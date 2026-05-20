#!/usr/bin/env python3
import os
import struct
import argparse
import hashlib
import json
import lzma
import shutil
from pathlib import Path

TABLE_START_OFFSET = 0x38
TABLE_ENTRY_SIZE = 0x60
FS_MARKER = b'\xFF\xFF\x00\x10\xFE\xCA'
NTLZ_OFFSET = 0x580000
NTLZ_SIZE = 0x10000
NTLZ_HEADER_SIZE = 0x60

class Partition:
    def __init__(self, index, name, next_name, offset, size, used_size, flags):
        self.index = index
        self.name = name
        self.next_name = next_name
        self.offset = offset
        self.size = size
        self.used_size = used_size
        self.flags = flags

def _u32le(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]

def _four_byte_name(raw: bytes) -> str:
    if raw == b"\xff\xff\xff\xff":
        return ""
    return raw[::-1].decode("latin1", errors="replace")

def parse_partitions(data: bytes):
    if len(data) < TABLE_START_OFFSET + TABLE_ENTRY_SIZE:
        raise ValueError("文件太小，不像 ASR ROM")
    if data[4:8] != b"HMIT":
        raise ValueError("未找到 HMIT 魔数，不支持的 ROM")
    
    count = _u32le(data, 0x2C)
    if not (1 <= count <= 64):
        raise ValueError(f"分区数量异常: {count}")
    
    partitions = []
    for i in range(count):
        off = TABLE_START_OFFSET + i * TABLE_ENTRY_SIZE
        entry = data[off:off + TABLE_ENTRY_SIZE]
        name = _four_byte_name(entry[0:4])
        next_name = _four_byte_name(entry[4:8]) or None
        
        offset = _u32le(entry, 8)
        flash_addr = _u32le(entry, 12)
        size = _u32le(entry, 16)
        used_size = _u32le(entry, 20)
        flags = _u32le(entry, 24)
        
        if offset > 0x10000000 and offset < 0x7FFFFFFF and size < 0x10000:
            offset, size = size, offset
        
        if offset > len(data) or (offset > 0 and size == 0):
            offset = _u32le(entry, 12)
            size = _u32le(entry, 16)
        
        if offset > len(data):
            continue
        
        partitions.append(Partition(i, name, next_name, offset, size, used_size, flags))
    
    return partitions

def find_next_marker(data: bytes, start_pos: int):
    CORE_MARKER = b'\x00\x10\xFE\xCA'
    
    pos = data.find(CORE_MARKER, start_pos)
    if pos == -1:
        return -1, 0, None
    
    marker_start = pos
    marker_len = 4
    
    if pos >= 2 and data[pos-2:pos] == b'\xFF\xFF':
        marker_start = pos - 2
        marker_len = 6
    elif pos >= 1 and data[pos-1:pos] in (b'\xFF', b'\x0A'):
        marker_start = pos - 1
        marker_len = 5
    elif pos >= 2 and data[pos-2:pos] == b'\x0D\x0A':
        marker_start = pos - 2
        marker_len = 6
    
    return marker_start, marker_len, data[marker_start:marker_start+marker_len]

def parse_ntlz_sizes(ntlz_data: bytes):
    """解析 NTLZ 分区中的文件大小索引表"""
    sizes = []
    for i in range(NTLZ_HEADER_SIZE, len(ntlz_data), 4):
        if i + 4 > len(ntlz_data):
            break
        
        file_size = struct.unpack('<I', ntlz_data[i:i+4])[0]
        
        if file_size == 0:
            all_zero = True
            for j in range(i, min(i + 16, len(ntlz_data)), 4):
                if struct.unpack('<I', ntlz_data[j:j+4])[0] != 0:
                    all_zero = False
                    break
            if all_zero:
                break
        
        sizes.append(file_size)
    
    return sizes

def parse_files_from_fs_data(data: bytes, base_offset: int = 0):
    results = []
    pos = 0
    max_file_size = 10485760
    
    while pos < len(data):
        marker_pos, marker_len, marker = find_next_marker(data, pos)
        
        if marker_pos == -1:
            break
        
        offset = marker_pos + marker_len
        
        if offset + 4 > len(data):
            pos = marker_pos + marker_len
            continue
        header = data[offset:offset+4]
        offset += 4
        
        name_start = offset
        name_end = data.find(b'\x00\x00', name_start)
        if name_end == -1:
            pos = marker_pos + marker_len
            continue
        
        file_name_bytes = data[name_start:name_end]
        try:
            file_name = file_name_bytes.decode('ascii', errors='ignore')
        except:
            pos = marker_pos + marker_len
            continue
        
        file_name = ''.join(c for c in file_name if c.isprintable() or c in '\\/')
        
        if not file_name or len(file_name) < 2:
            pos = marker_pos + marker_len
            continue
        
        content_start = name_end + 2
        
        next_marker_pos, _, _ = find_next_marker(data, content_start)
        if next_marker_pos == -1:
            next_marker_pos = len(data)
        
        content_end = next_marker_pos
        
        file_content = data[content_start:content_end]
        
        original_content = file_content
        
        stripped_content = file_content
        if len(file_content) > 0:
            zero_count = 0
            while zero_count < len(file_content) and file_content[zero_count] == 0:
                zero_count += 1
            
            if zero_count > 0 and zero_count < len(file_content):
                header_found = None
                for hdr in [b'<?xml', b'<', b'var ', b'function', b'.', b'@import']:
                    search_end = min(zero_count + 200, len(file_content))
                    p = file_content.find(hdr, zero_count, search_end)
                    if p != -1 and (header_found is None or p < header_found):
                        header_found = p
                for hdr in [b'\x89PNG', b'\xFF\xD8\xFF', b'GIF', b'\x00\x00\x01\x00']:
                    search_end = min(zero_count + 200, len(file_content))
                    p = file_content.find(hdr, zero_count, search_end)
                    if p != -1 and (header_found is None or p < header_found):
                        header_found = p
                lzma_header = b'\x5D\x00\x00'
                search_end = min(zero_count + 200, len(file_content))
                p = file_content.find(lzma_header, zero_count, search_end)
                if p != -1 and (header_found is None or p < header_found):
                    header_found = p
                
                if header_found is not None:
                    stripped_content = file_content[header_found:]
        
        if len(stripped_content) > 0 and len(stripped_content) <= max_file_size:
            results.append({
                'filename': file_name,
                'file_size': len(original_content),
                'content_offset': base_offset + content_start,
                'content_end': base_offset + content_end,
                'content_length': len(stripped_content),
                'marker_offset': base_offset + marker_pos,
                'content': stripped_content,
                'original_size': len(original_content),
                'marker_length': marker_len,
                'header_bytes': header
            })
        
        pos = next_marker_pos
    
    return results

def split_content_by_filenames(content: bytes):
    results = []
    
    pattern = b'www\\\\'
    positions = []
    
    search_pos = 0
    while True:
        search_pos = content.find(pattern, search_pos)
        if search_pos == -1:
            break
        positions.append(search_pos)
        search_pos += len(pattern)
    
    if not positions:
        return [content]
    
    start = 0
    for pos in positions:
        if pos > start:
            results.append(content[start:pos])
        start = pos
    
    if start < len(content):
        end_pos = content.find(b'\x00\x00', start)
        if end_pos != -1:
            end_pos = content.find(b'\x00\x00', end_pos + 2)
            if end_pos != -1:
                results.append(content[start:end_pos])
        else:
            results.append(content[start:])
    
    return results

def extract_firmware(firmware_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    with open(firmware_path, 'rb') as f:
        data = f.read()
    
    file_size = len(data)
    print(f"固件大小: 0x{file_size:x} ({file_size} 字节)")
    
    partitions = parse_partitions(data)
    print(f"找到 {len(partitions)} 个分区:")
    
    partitions_dir = os.path.join(output_dir, 'partitions')
    files_dir = os.path.join(output_dir, 'files')
    os.makedirs(partitions_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)
    
    shutil.copy2(firmware_path, os.path.join(output_dir, 'rom_original.bin'))
    
    for part in partitions:
        print(f"  [{part.index}] {part.name}: 偏移=0x{part.offset:x}, 大小=0x{part.size:x}")
        
        part_data = data[part.offset:part.offset+part.size]
        safe_name = f"{part.index:02d}_{part.name}"
        part_path = os.path.join(partitions_dir, f"{safe_name}.bin")
        with open(part_path, 'wb') as out:
            out.write(part_data)
    
    ntlz_sizes = []
    if NTLZ_OFFSET < len(data):
        ntlz_data = data[NTLZ_OFFSET:NTLZ_OFFSET+NTLZ_SIZE]
        ntlz_sizes = parse_ntlz_sizes(ntlz_data)
        print(f"\nNTLZ 文件大小索引: {len(ntlz_sizes)} 个条目")
    
    filesystem_partition = None
    filesystem_names = ['NTLZ', 'ROOT', 'FSYS', 'FILES', 'SYSFS', 'WEB']
    
    for name in filesystem_names:
        for part in partitions:
            if part.name == name:
                filesystem_partition = part
                break
        if filesystem_partition:
            break
    
    print("\n搜索文件系统标记...")
    CORE_MARKER = b'\x00\x10\xFE\xCA'
    first_marker_pos = data.find(CORE_MARKER)
    
    if first_marker_pos != -1:
        print(f"找到文件系统标记，第一个位置: 0x{first_marker_pos:x}")
        
        last_marker_pos = data.rfind(CORE_MARKER)
        fs_offset = max(0, first_marker_pos - 1024)
        fs_end = min(len(data), last_marker_pos + 1024 + 1048576)
        
        print(f"搜索范围: 0x{fs_offset:x} - 0x{fs_end:x}")
    elif filesystem_partition:
        print(f"使用文件系统分区: {filesystem_partition.name}")
        fs_offset = filesystem_partition.offset
        fs_end = filesystem_partition.offset + filesystem_partition.size
    else:
        print("警告: 未找到文件系统标记和已知分区，将搜索整个固件")
        fs_offset = 0
        fs_end = len(data)
    
    all_files = parse_files_from_fs_data(data[fs_offset:fs_end], fs_offset)
    
    seen = set()
    unique_files = []
    for f in all_files:
        key = (f['filename'], f['content_offset'])
        if key not in seen:
            seen.add(key)
            unique_files.append(f)
    
    print(f"找到 {len(unique_files)} 个文件系统文件")
    
    manifest_entries = []
    file_index = 0
    
    for f_info in unique_files:
        clean_filename = f_info['filename'].replace('\\', '/')
        if clean_filename.startswith('/'):
            clean_filename = clean_filename[1:]
        
        output_path = os.path.join(files_dir, clean_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'wb') as out:
            out.write(f_info['content'])
        
        ntlz_index = file_index if file_index < len(ntlz_sizes) else -1
        ntlz_size = ntlz_sizes[file_index] if file_index < len(ntlz_sizes) else 0
        
        manifest_entries.append({
            'filename': f_info['filename'],
            'file_size': f_info['file_size'],
            'content_offset': f_info['content_offset'],
            'content_length': f_info['content_length'],
            'marker_offset': f_info['marker_offset'],
            'marker_length': f_info['marker_length'],
            'header_bytes': f_info['header_bytes'].hex(),
            'ntlz_index': ntlz_index,
            'ntlz_size': ntlz_size
        })
        
        file_index += 1
    
    manifest = {
        "format": "ASR_TIMH_SPI_NOR_FULL_DUMP",
        "source_file": firmware_path,
        "file_size": file_size,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "partition_count": len(partitions),
        "ntlz_size_count": len(ntlz_sizes),
        "partitions": [
            {
                "index": p.index,
                "name": p.name,
                "offset": p.offset,
                "size": p.size
            } for p in partitions
        ],
        "files": manifest_entries
    }
    
    with open(os.path.join(output_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"\n提取完成！")
    print(f"  分区文件: {partitions_dir}")
    print(f"  文件系统文件: {files_dir} (共 {len(all_files)} 个文件)")
    print(f"  NTLZ 索引条目: {len(ntlz_sizes)} 个")

def pack_firmware(input_dir, output_path, update_ntlz=True):
    input_dir = Path(input_dir)
    output_path = Path(output_path)
    
    with open(input_dir / 'manifest.json', 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    rom = bytearray((input_dir / 'rom_original.bin').read_bytes())
    files_dir = input_dir / 'files'
    
    ntlz_data = bytearray(rom[NTLZ_OFFSET:NTLZ_OFFSET+NTLZ_SIZE])
    
    for file_index, file_info in enumerate(manifest.get('files', [])):
        clean_filename = file_info['filename'].replace('\\', '/')
        if clean_filename.startswith('/'):
            clean_filename = clean_filename[1:]
        
        file_path = files_dir / clean_filename
        if not file_path.exists():
            continue
        
        with open(file_path, 'rb') as f:
            new_content = f.read()
        
        content_offset = file_info['content_offset']
        original_content_length = file_info['content_length']
        original_file_size = file_info['file_size']
        
        marker_offset = file_info['marker_offset']
        marker_length = file_info['marker_length']
        header_bytes = bytes.fromhex(file_info['header_bytes'])
        
        name_start = marker_offset + marker_length + 4
        name_end = rom.find(b'\x00\x00', name_start)
        if name_end == -1:
            continue
        
        content_start = name_end + 2
        content_end = content_start + original_file_size
        
        if content_end > len(rom):
            content_end = len(rom)
        
        padding_needed = content_end - content_start - len(new_content)
        
        if padding_needed >= 0:
            new_content_with_padding = new_content + b'\x00' * padding_needed
            rom[content_start:content_start+len(new_content_with_padding)] = new_content_with_padding
        else:
            print(f"警告: {clean_filename} 新内容超过原始空间，截断到原始大小")
            rom[content_start:content_end] = new_content[:content_end-content_start]
        
        new_size = len(new_content)
        
        if update_ntlz and 'ntlz_index' in file_info and file_info['ntlz_index'] >= 0:
            ntlz_idx = file_info['ntlz_index']
            size_offset = NTLZ_HEADER_SIZE + ntlz_idx * 4
            if size_offset + 4 <= len(ntlz_data):
                ntlz_data[size_offset:size_offset+4] = struct.pack('<I', new_size)
    
    if update_ntlz:
        rom[NTLZ_OFFSET:NTLZ_OFFSET+len(ntlz_data)] = ntlz_data
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    
    print(f"打包完成: {output_path}")
    print(f"SHA256: {hashlib.sha256(rom).hexdigest()}")
    if update_ntlz:
        print("已更新 NTLZ 文件大小索引")

def main():
    parser = argparse.ArgumentParser(description='ASR Firmware Tool')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    extract_parser = subparsers.add_parser('extract', help='Extract firmware partitions and files')
    extract_parser.add_argument('firmware', help='Path to firmware file')
    extract_parser.add_argument('output', help='Output directory')
    
    pack_parser = subparsers.add_parser('pack', help='Pack firmware from extracted files')
    pack_parser.add_argument('input', help='Input directory containing extracted files')
    pack_parser.add_argument('output', help='Output firmware file')
    pack_parser.add_argument('--no-ntlz', action='store_true', help='Do not update NTLZ size index')
    
    args = parser.parse_args()
    
    if args.command == 'extract':
        extract_firmware(args.firmware, args.output)
    elif args.command == 'pack':
        pack_firmware(args.input, args.output, update_ntlz=not args.no_ntlz)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()