#!/usr/bin/env python3
import argparse

PSM_MARKER = b'psm.dat'
CONFIG_MARKER = b'WMG88.'
VALUE_SEPARATOR = '='
ENTRY_SEPARATOR = ';'

class PsmDat:
    def __init__(self, firmware_path):
        self.firmware_path = firmware_path
        self.data = None
        self.config = {}
        self.content_start = 0
        self.content_end = 0
    
    def load(self):
        with open(self.firmware_path, 'rb') as f:
            self.data = f.read()
        
        psm_pos = self.data.find(PSM_MARKER)
        if psm_pos == -1:
            raise ValueError("未找到 psm.dat 标记")
        
        config_pos = self.data.find(CONFIG_MARKER, psm_pos)
        if config_pos == -1:
            raise ValueError("未找到配置数据标记 WMG88.")
        
        self.content_start = config_pos
        
        content_end = self.data.find(b'\xff\xff\xff\xff', self.content_start)
        if content_end == -1:
            content_end = self.data.find(b'\x00\x00\x00\x00', self.content_start)
        if content_end == -1:
            content_end = self.find_next_file_marker(self.content_start)
        if content_end == -1:
            content_end = min(len(self.data), self.content_start + 8000)
        
        self.content_end = content_end
        config_data = self.data[self.content_start:self.content_end]
        
        self.parse_config(config_data)
        
        return self
    
    def find_next_file_marker(self, start_pos):
        file_markers = [b'\xff\xff\x00\x10\xfe\xca', b'\xff\x00\x10\xfe\xca', b'\x0a\x00\x10\xfe\xca', b'\x00\x10\xfe\xca']
        min_pos = -1
        for marker in file_markers:
            pos = self.data.find(marker, start_pos + 100)
            if pos != -1 and (min_pos == -1 or pos < min_pos):
                min_pos = pos
        return min_pos
    
    def parse_config(self, config_data):
        self.config = {}
        try:
            config_str = config_data.decode('ascii', errors='replace')
            entries = config_str.split(ENTRY_SEPARATOR)
            for entry in entries:
                entry = entry.strip()
                if entry and VALUE_SEPARATOR in entry:
                    key, value = entry.split(VALUE_SEPARATOR, 1)
                    key = key.strip()
                    value = value.strip()
                    if key and key.isprintable():
                        self.config[key] = value
        except Exception as e:
            print(f"解析配置时出错: {e}")
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = str(value)
    
    def remove(self, key):
        if key in self.config:
            del self.config[key]
    
    def save(self, output_path=None):
        if output_path is None:
            output_path = self.firmware_path
        
        new_content = self.serialize_config()
        new_content_bytes = new_content.encode('ascii')
        
        available_space = self.content_end - self.content_start
        padding_needed = available_space - len(new_content_bytes)
        
        if padding_needed >= 0:
            final_content = new_content_bytes + b'\x00' * padding_needed
        else:
            print(f"警告: 新配置超出原始空间 ({len(new_content_bytes)} > {available_space})")
            final_content = new_content_bytes[:available_space]
        
        result = bytearray(self.data)
        result[self.content_start:self.content_start + len(final_content)] = final_content
        
        with open(output_path, 'wb') as f:
            f.write(result)
        
        print(f"已保存到 {output_path}")
        print(f"原始大小: {available_space} 字节")
        print(f"新大小: {len(new_content)} 字节")
    
    def serialize_config(self):
        entries = []
        for key, value in sorted(self.config.items()):
            entries.append(f"{key}={value}")
        return ENTRY_SEPARATOR.join(entries)
    
    def list_keys(self, filter_pattern=None):
        keys = list(self.config.keys())
        if filter_pattern:
            keys = [k for k in keys if filter_pattern.lower() in k.lower()]
        return sorted(keys)
    
    def print_config(self, filter_pattern=None):
        keys = self.list_keys(filter_pattern)
        for key in keys:
            value = self.config[key]
            print(f"{key} = {value}")

def main():
    parser = argparse.ArgumentParser(description='PSM.dat 运行时数据工具')
    parser.add_argument('firmware', help='固件文件路径')
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    list_parser = subparsers.add_parser('list', help='列出所有配置项')
    list_parser.add_argument('--filter', help='过滤关键字')
    
    get_parser = subparsers.add_parser('get', help='获取配置项')
    get_parser.add_argument('key', help='配置项键名')
    
    set_parser = subparsers.add_parser('set', help='设置配置项')
    set_parser.add_argument('key', help='配置项键名')
    set_parser.add_argument('value', help='配置项值')
    set_parser.add_argument('-o', '--output', help='输出固件路径')
    
    delete_parser = subparsers.add_parser('delete', help='删除配置项')
    delete_parser.add_argument('key', help='配置项键名')
    delete_parser.add_argument('-o', '--output', help='输出固件路径')
    
    export_parser = subparsers.add_parser('export', help='导出配置到文件')
    export_parser.add_argument('output', help='输出文件路径')
    
    import_parser = subparsers.add_parser('import', help='从文件导入配置')
    import_parser.add_argument('input', help='输入配置文件')
    import_parser.add_argument('-o', '--output', help='输出固件路径')
    
    args = parser.parse_args()
    
    psm = PsmDat(args.firmware).load()
    
    if args.command == 'list':
        psm.print_config(args.filter)
    
    elif args.command == 'get':
        value = psm.get(args.key)
        if value is not None:
            print(value)
        else:
            print(f"未找到键: {args.key}")
    
    elif args.command == 'set':
        psm.set(args.key, args.value)
        output = args.output if args.output else args.firmware + '.modified.bin'
        psm.save(output)
        print(f"已设置 {args.key} = {args.value}")
    
    elif args.command == 'delete':
        psm.remove(args.key)
        output = args.output if args.output else args.firmware + '.modified.bin'
        psm.save(output)
        print(f"已删除 {args.key}")
    
    elif args.command == 'export':
        content = psm.serialize_config()
        with open(args.output, 'w') as f:
            f.write(content)
        print(f"已导出到 {args.output}")
    
    elif args.command == 'import':
        with open(args.input, 'r') as f:
            content = f.read()
        psm.parse_config(content.encode('ascii'))
        output = args.output if args.output else args.firmware + '.modified.bin'
        psm.save(output)
        print(f"已从 {args.input} 导入配置")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()