# ASR 固件解包和打包工具

本工具集用于解包、修改和重新打包 ASR 路由器固件（LB031_N12.bin）。

## 工具列表

| 工具 | 功能 |
|------|------|
| `firmware_tool.py` | 提取和打包固件文件（核心工具，支持 NTLZ 大小索引更新） |
| `batch_decompress_lzma.py` | 批量解压 LZMA 压缩文件 |
| `batch_compress_lzma.py` | 批量压缩文件为 LZMA 格式 |
| `psm_tool.py` | 读取和更新运行时数据（psm.dat） |

## 完整工作流程

### 第一步：提取固件

```bash
python firmware_tool.py extract <固件文件> <输出目录>
```

示例：
```bash
python firmware_tool.py extract asr/LB031_N12.bin firmware_extracted
```

提取后会生成以下内容：
```
firmware_extracted/
├── manifest.json          # 文件清单（包含所有文件的位置信息和 NTLZ 索引）
├── rom_original.bin       # 原始固件备份
├── partitions/            # 分区原始文件
│   ├── 00_TIMH.bin
│   ├── 01_OBMI.bin
│   ├── 07_NTLZ.bin        # 文件系统索引分区（包含文件大小表）
│   └── ...
└── files/                 # 提取的文件系统文件
    └── www/
        ├── defaults/       # XML 配置文件
        ├── html/           # HTML 页面（部分为 LZMA 压缩）
        ├── js/             # JavaScript 文件（LZMA 压缩）
        ├── css/            # CSS 文件（LZMA 压缩）
        ├── images/         # 图片文件
        └── xmldata/        # XML 数据文件
```

### 第二步：批量解压 LZMA 文件

固件中包含多个 `.lzma` 压缩文件，需要先解压才能编辑。

```bash
python batch_decompress_lzma.py <提取目录>/files <解压目录>
```

示例：
```bash
python batch_decompress_lzma.py firmware_extracted/files firmware_decompressed
```

解压后的文件会保存在 `firmware_decompressed` 目录，文件扩展名会去掉 `.lzma`。

### 第三步：编辑文件

直接编辑解压后的文件：

| 文件类型 | 路径 | 是否压缩 |
|----------|------|----------|
| HTML 文件 | `www/html/*.html` | 是（LZMA） |
| JavaScript 文件 | `www/js/*.js` | 是（LZMA） |
| CSS 文件 | `www/css/*.css` | 是（LZMA） |
| XML 配置 | `www/defaults/*.xml` | 否 |
| XML 数据 | `www/xmldata/*.xml` | 否 |
| 图片 | `www/images/*.png` | 否 |

### 第四步：重新压缩 LZMA 文件

```bash
python batch_compress_lzma.py <解压目录> <重新压缩目录> <原始文件目录>
```

示例：
```bash
python batch_compress_lzma.py firmware_decompressed firmware_recompressed firmware_extracted/files
```

此命令会：
1. 将修改后的 LZMA 源文件重新压缩
2. 直接复制非压缩文件（如 XML、图片等）

### 第五步：重新打包固件

```bash
python firmware_tool.py pack <提取目录> <输出固件>
```

示例：
```bash
python firmware_tool.py pack firmware_extracted asr/LB031_N12_modified.bin
```

**重要**：打包前需要将重新压缩的文件复制到 `<提取目录>/files` 目录，覆盖原文件。

完整示例：
```bash
# 复制重新压缩的文件到提取目录
xcopy firmware_recompressed\* firmware_extracted\files\ /E /Y

# 打包固件（自动更新 NTLZ 大小索引）
python firmware_tool.py pack firmware_extracted asr/LB031_N12_modified.bin
```

## NTLZ 文件大小索引

### 概述

NTLZ 分区（偏移 0x580000，大小 0x10000）包含一个文件大小索引表：

| 字段 | 偏移 | 大小 | 说明 |
|------|------|------|------|
| 文件数量 | 0x00 | 4 字节 | 小端序 |
| 索引表大小 | 0x04 | 4 字节 | 小端序 |
| 版本 | 0x08 | 4 字节 | 小端序 |
| 头部大小 | 0x0C | 4 字节 | 小端序 |
| ... | ... | ... | 其他头部字段 |
| 文件大小数组 | 0x60 | 可变 | 每个条目 4 字节，小端序 |

### 索引更新机制

打包时工具会自动更新 NTLZ 分区中的文件大小索引：

1. **提取阶段**：记录每个文件对应的 NTLZ 索引位置（`ntlz_index`）
2. **打包阶段**：根据修改后文件的实际大小更新对应索引

### 跳过 NTLZ 更新

如果不需要更新 NTLZ 索引，可以使用 `--no-ntlz` 参数：

```bash
python firmware_tool.py pack --no-ntlz firmware_extracted asr/LB031_N12_modified.bin
```

## 验证修改

打包后可以验证修改是否成功：

```bash
# 提取修改后的固件
python firmware_tool.py extract asr/LB031_N12_modified.bin verify_extracted

# 解压 LZMA 文件
python batch_decompress_lzma.py verify_extracted/files verify_decompressed

# 检查修改内容
type verify_decompressed\www\html\m_dashboard.html
```

## 文件系统结构

固件使用特殊的文件系统格式：

| 组件 | 说明 |
|------|------|
| 分区表 (TIMH) | 定义固件中各个分区的位置和大小 |
| 文件系统分区 | NTLZ 分区（偏移 0x580000，大小 0x10000） |
| 文件系统标记 | `\xFF\xFF\x00\x10\xFE\xCA` 或其他变体标识每个文件的开始 |
| 文件结构 | `[标记] + [4字节标识] + [文件名] + \x00\x00 + [文件内容]` |
| LZMA 格式 | 使用 LZMA FORMAT_ALONE 格式（头部 `0x5D 0x00 0x00`） |

## 重要限制 ⚠️

### 文件大小限制

**关键限制**：修改后的文件重新压缩后的大小**必须小于等于**原始 LZMA 文件大小。

原因：
1. 每个文件在固件中有固定的存储空间
2. 无法扩展文件空间（受固件分区大小限制）
3. LZMA 压缩率取决于内容，修改后可能变大

### 推荐做法

1. **保持修改最小化**：只修改必要的内容
2. **压缩优化**：移除不必要的空格、注释、空行
3. **测试压缩**：在打包前先测试压缩后的大小
4. **保留备份**：始终保留原始固件的备份

### LZMA 压缩级别

默认使用 LZMA 最高压缩级别（9级），以获得最小的压缩结果。

## 特殊说明

### LZMA 文件格式

固件中的 LZMA 文件使用嵌入式设备专用格式：

| 特性 | 说明 |
|------|------|
| 魔术字节 | `0x5D 0x00 0x00`（标准 LZMA 单独格式） |
| 未压缩大小 | 通常为 0（由文件系统外部管理） |
| 命令行工具 | 标准 `lzma`/`xz` 命令可能无法直接解压 |
| Python | 使用 Python 的 `lzma` 模块可以正确解压 |

### 前导零填充处理

工具会自动处理文件中的前导零填充：

| 文件类型 | 处理方式 |
|----------|----------|
| XML 文件 | 自动去除前导零 |
| HTML/JS/CSS | 自动去除前导零 |
| 图片文件 | 自动去除前导零 |
| LZMA 文件 | 自动去除前导零，保留标准格式 |

### 重复文件处理

固件中部分文件可能存在多个副本（如 `mTrafficStatistical.html.lzma`），工具会：
- 提取所有唯一文件
- 打包时更新所有相关的 NTLZ 索引
- 确保所有副本保持一致

## 完整修改示例

```bash
# 1. 提取固件
python firmware_tool.py extract asr/LB031_N12.bin firmware_extracted

# 2. 解压 LZMA 文件
python batch_decompress_lzma.py firmware_extracted/files firmware_decompressed

# 3. 编辑文件（示例：修改首页标题）
# 使用文本编辑器打开 firmware_decompressed/www/html/m_dashboard.html
# 修改相关内容

# 4. 重新压缩
python batch_compress_lzma.py firmware_decompressed firmware_recompressed firmware_extracted/files

# 5. 复制回提取目录
xcopy firmware_recompressed\* firmware_extracted\files\ /E /Y

# 6. 重新打包（自动更新 NTLZ 索引）
python firmware_tool.py pack firmware_extracted asr/LB031_N12_modified.bin

# 7. 验证
python firmware_tool.py extract asr/LB031_N12_modified.bin verify_extracted
python batch_decompress_lzma.py verify_extracted/files verify_decompressed
```

## 工具使用说明

### firmware_tool.py

```bash
# 提取固件
python firmware_tool.py extract <固件文件> <输出目录>

# 打包固件（自动更新 NTLZ 索引）
python firmware_tool.py pack <提取目录> <输出固件>

# 打包固件（不更新 NTLZ 索引）
python firmware_tool.py pack --no-ntlz <提取目录> <输出固件>
```

### batch_decompress_lzma.py

```bash
python batch_decompress_lzma.py <输入目录> <输出目录>
```

### batch_compress_lzma.py

```bash
python batch_compress_lzma.py <解压目录> <输出目录> <原始文件目录>
```

### psm_tool.py

运行时数据（psm.dat）管理工具，用于读取和修改路由器的持久化状态配置。

```bash
# 列出所有配置项
python psm_tool.py <固件文件> list

# 过滤显示特定配置
python psm_tool.py <固件文件> list --filter management

# 获取单个配置项
python psm_tool.py <固件文件> get <配置键名>

# 设置配置项
python psm_tool.py <固件文件> set <配置键名> <值> [-o <输出固件>]

# 删除配置项
python psm_tool.py <固件文件> delete <配置键名> [-o <输出固件>]

# 导出配置到文件
python psm_tool.py <固件文件> export <输出文件>

# 从文件导入配置
python psm_tool.py <固件文件> import <输入文件> [-o <输出固件>]
```

示例：

```bash
# 查看管理配置
python psm_tool.py asr/LB031_N12.bin list --filter management

# 查看路由器密码
python psm_tool.py asr/LB031_N12.bin get WMG88.management.router_password

# 修改路由器密码
python psm_tool.py asr/LB031_N12.bin set WMG88.management.router_password MyNewPass123 -o modified.bin

# 查看 WiFi 配置
python psm_tool.py asr/LB031_N12.bin list --filter wlan

# 查看系统信息
python psm_tool.py asr/LB031_N12.bin get WMG88.sysinfo.serial_number

# 导出所有配置
python psm_tool.py asr/LB031_N12.bin export config_backup.txt
```

常见配置项：

| 配置项 | 说明 |
|--------|------|
| `WMG88.management.router_username` | 管理用户名 |
| `WMG88.management.router_password` | 管理密码 |
| `WMG88.management.httpd_port` | HTTP 端口 |
| `WMG88.wlan_security.ssid` | WiFi 名称 |
| `WMG88.wlan_security.key` | WiFi 密码 |
| `WMG88.sysinfo.serial_number` | 序列号 |
| `WMG88.device_management.factory_state` | 出厂状态 |

## 常见问题

### Q: 修改后的文件太大怎么办？
A: 可以尝试：
1. 移除不必要的空格、注释
2. 简化代码逻辑
3. 使用更小的图片（如果是图片文件）
4. 删除不需要的功能模块

### Q: 如何查看 LZMA 文件内容？
A: 使用 `batch_decompress_lzma.py` 批量解压后查看。命令行工具（如 `lzma`/`xz`）可能无法直接解压，需要使用 Python。

### Q: 为什么命令行工具无法解压 LZMA 文件？
A: 固件中的 LZMA 文件使用特殊格式（未压缩大小字段为 0），需要使用 Python 的 `lzma` 模块来解压。

### Q: 打包失败怎么办？
A: 检查：
1. manifest.json 是否存在且完整
2. 修改的文件路径是否正确
3. 修改后的文件是否超出原始空间
4. 是否有文件被意外删除

### Q: 验证流程是什么？
A: 完整验证流程：
1. 解包原始固件
2. 解压 LZMA 文件
3. 重新压缩（不修改）
4. 重新打包
5. 解包新固件验证

### Q: NTLZ 索引有什么作用？
A: NTLZ 索引表存储了每个文件的大小信息，固件运行时使用这些索引快速定位和读取文件。修改文件后更新索引可确保固件正确加载文件。

## 技术支持

如果遇到问题，请检查：
1. 所有 Python 脚本是否在同一目录
2. Python 版本是否 >= 3.6
3. 是否安装了必要的依赖（`lzma` 模块为 Python 内置）
4. 命令参数是否正确

## 验证状态

✅ **已验证**：完整的解包→修改→打包→验证流程已成功测试
- 固件大小保持一致（8388608 字节）
- 文件数量完全匹配（368 个文件系统文件）
- 分区结构保持不变（9 个分区）
- NTLZ 大小索引正确更新
- 所有文件类型的前导零填充已正确处理
- LZMA 文件格式已正确识别和处理