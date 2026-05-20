#!/usr/bin/env python3

import os
import lzma
import argparse

def decompress_lzma_file(input_path, output_path):
    try:
        with open(input_path, 'rb') as f:
            compressed_data = f.read()
        
        if len(compressed_data) < 3:
            return False, "文件太小"
        
        offset = 0
        while offset < len(compressed_data) - 2 and compressed_data[offset:offset+3] != b'\x5d\x00\x00':
            offset += 1
        
        if offset >= len(compressed_data) - 2:
            return False, "不是有效的 LZMA FORMAT_ALONE 格式"
        
        if offset > 0:
            compressed_data = compressed_data[offset:]
        
        decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        decompressed_data = decompressor.decompress(compressed_data)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(decompressed_data)
        
        return True, f"解压成功: {len(compressed_data)} -> {len(decompressed_data)} 字节"
    
    except Exception as e:
        return False, f"解压失败: {str(e)}"

def batch_decompress(input_dir, output_dir):
    lzma_count = 0
    success_count = 0
    fail_count = 0
    
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            if filename.lower().endswith('.lzma'):
                lzma_count += 1
                input_path = os.path.join(root, filename)
                
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path[:-5])
                
                success, message = decompress_lzma_file(input_path, output_path)
                
                if success:
                    success_count += 1
                    print(f"✅ {rel_path} -> {message}")
                else:
                    fail_count += 1
                    print(f"❌ {rel_path} -> {message}")
    
    print(f"\n=== 解压完成 ===")
    print(f"总文件数: {lzma_count}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='批量解压 LZMA 文件')
    parser.add_argument('input_dir', help='输入目录（包含 .lzma 文件）')
    parser.add_argument('output_dir', help='输出目录')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.input_dir):
        print(f"错误: 输入目录 '{args.input_dir}' 不存在")
        exit(1)
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    batch_decompress(args.input_dir, args.output_dir)