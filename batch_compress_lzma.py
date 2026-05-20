#!/usr/bin/env python3

import os
import lzma
import argparse

def compress_to_lzma(input_path, output_path):
    try:
        with open(input_path, 'rb') as f:
            raw_data = f.read()
        
        compressed_data = lzma.compress(raw_data, format=lzma.FORMAT_ALONE)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(compressed_data)
        
        return True, f"压缩成功: {len(raw_data)} -> {len(compressed_data)} 字节"
    
    except Exception as e:
        return False, f"压缩失败: {str(e)}"

def batch_compress(input_dir, output_dir, original_files_dir):
    compress_count = 0
    success_count = 0
    fail_count = 0
    
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            input_path = os.path.join(root, filename)
            
            rel_path = os.path.relpath(input_path, input_dir)
            lzma_path = os.path.join(output_dir, rel_path + '.lzma')
            
            original_lzma_path = os.path.join(original_files_dir, rel_path + '.lzma')
            
            if os.path.exists(original_lzma_path):
                compress_count += 1
                success, message = compress_to_lzma(input_path, lzma_path)
                
                if success:
                    success_count += 1
                    print(f"✅ {rel_path} -> {message}")
                else:
                    fail_count += 1
                    print(f"❌ {rel_path} -> {message}")
            else:
                target_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(input_path, 'rb') as src:
                    with open(target_path, 'wb') as dst:
                        dst.write(src.read())
                print(f"📄 {rel_path} -> 直接复制（非 LZMA 文件）")
    
    print(f"\n=== 压缩完成 ===")
    print(f"压缩文件数: {compress_count}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='批量压缩文件为 LZMA 格式')
    parser.add_argument('input_dir', help='输入目录（包含解压后的文件）')
    parser.add_argument('output_dir', help='输出目录（保存压缩后的文件）')
    parser.add_argument('original_files_dir', help='原始文件目录（用于确定哪些文件需要压缩）')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.input_dir):
        print(f"错误: 输入目录 '{args.input_dir}' 不存在")
        exit(1)
    
    if not os.path.isdir(args.original_files_dir):
        print(f"错误: 原始文件目录 '{args.original_files_dir}' 不存在")
        exit(1)
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    batch_compress(args.input_dir, args.output_dir, args.original_files_dir)