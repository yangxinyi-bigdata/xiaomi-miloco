# Xiaomi Miloco

智能家居未来探索方案 **Xiaomi Local Copilot** ，以米家摄像机为视觉信息来源，以自研大模型为核心，打通全屋 IoT 设备。基于大模型的开发范式，让用户能够以自然语言定义家庭的各种需求和规则，实现更广泛、更具创意的智能联动。

<div align="center">

简体中文 | [English](README_en.md)

</div>

## 最新动态

- [2025-11] Xiaomi Miloco 整体框架开源

## 本项目相比上游的主要修改 (Fork Modifications)

本项目是从 `XiaoMi/xiaomi-miloco` 上游 Fork 出来的版本，并包含了以下独有修改与优化：
1. **支持设置“生效时间段”**：现在你可以为触发规则设置具体的时间段啦（甚至支持跨天）。同时，日志里也会更清晰地告诉你每条规则为什么没执行、具体卡在了哪一步。
2. **告别“重复报错”刷屏**：优化了错误日志的显示。如果某个问题一直出现，系统不再疯狂刷屏，而是把同一错误的发生时间实时刷新到最新，让日志页面更清爽、更准确。
3. **更稳定的任务执行日志**：修复了后台任务偶尔“跑得太快”导致日志状态更新失败的小毛病，现在的执行记录更加准确可靠。
4. **你的自定义配置终于能存住了**：修复了以前修改配置文件重启后可能失效、甚至导致系统崩溃的问题。现在你的所有自定义参数和提示词都会安全地保存在本地，无论怎么更新系统都不会丢！
5. **底层框架小升级**：跟进了相关底层依赖库的新版本，保证系统跑得更稳。

## 关键特性

1. **交互新范式**：基于大模型的开发范式，通过自然语言交互就可以完成规则设置、设备的复杂指令控制。
2. **端侧大模型**：将家庭场景任务拆分规划+视觉理解两个阶段，提供小米自研端侧模型[Xiaomi MiMo-VL-Miloco-7B](https://github.com/XiaoMi/xiaomi-mimo-vl-miloco)，实现端侧视频理解，保障家庭隐私安全。
3. **视觉数据新用途**：以摄像头数据流作为感知信息源，使用大模型将视觉数据包含的各种家庭场景事件解析出来，用于回复用户 Query。
4. **米家生态**：打通米家生态，支持米家设备、米家场景的获取与执行，支持自定义内容发送米家通知。

    <img src="assets/images/ai_center_cn.jpg" width="60%" />

## 快速开始

### 系统要求

- **硬件要求**
```Plain Text
CPU: x64 架构
显卡: NVIDIA 30系及以上显卡，显存 8GB 及以上（最低），建议 12GB 及以上
存储: 建议 16GB 及以上可用空间（用于本地模型存储）
```

- **软件要求**
```Plain Text
操作系统:
  - Linux: x64 架构，建议 Ubuntu 22.04 及以上 LTS 版本
  - Windows: x64 架构，建议 Windows 10 及以上版本，要求支持 WSL2
  - macOS: 暂不支持
Docker: 20.10 及以上版本，需要支持 docker compose
NVIDIA 驱动: 支持 CUDA 的 NVIDIA 驱动
NVIDIA Container Toolkit: 用于Docker GPU支持
```

### 安装步骤

> **注意**: 请确保您的系统满足上述硬件和软件要求。windows 系统需要进入 wsl 环境。

**Docker 安装（推荐）**

如果你想快速体验，最简单的方式是通过源码中的一键安装脚本：

1. 克隆本项目代码到本地并进入目录：
```bash
git clone https://github.com/yangxinyi-bigdata/xiaomi-miloco.git
cd xiaomi-miloco
```

2. 运行一键安装脚本（脚本会自动拉取最新的 Docker 镜像并启动服务）：
```bash
bash scripts/install.sh
```
> **提示**：在安装过程的交互提示中，选择 `1. GitHub Packages` 作为镜像来源，脚本便会自动拉取 `ghcr.io/yangxinyi-bigdata/` 命名空间下咱们专属构建的镜像。

3. （可选）如果你需要手动拉取后端镜像，可执行：
```bash
docker pull ghcr.io/yangxinyi-bigdata/miloco-backend:latest
```
详细的安装步骤请参考 [Docker部署文档](docs/environment-setup_zh-Hans.md)。

**源码安装**
源码安装步骤请参考 [开发指南](docs/development/developer-setup_zh_Hans.md)。

## 使用教程文档

请参考 [使用文档](docs/usage/README_zh_Hans.md)。

## 贡献指南

请参考 [贡献指南](CONTRIBUTING.zh_Hans.md)。

## 许可证

许可证详情请查看 [LICENSE.md](LICENSE.md)。

**重要提示**: 本项目仅限非商业用途使用。未经小米公司书面授权，不得将本项目用于开发应用程序、Web服务或其他形式的软件。

## 安全问题
如果你在该项目中发现潜在的安全问题，或你认为可能发现了安全问题，请通过我们的漏洞报告邮箱通知[ Miloco 团队](xiaomi-miloco@xiaomi.com)。 请不要创建公开的 GitHub Issue

## 联系我们

### 问题反馈

如有问题反馈，请通过以下方式参与：
- 提交 [GitHub Issue](https://github.com/XiaoMi/xiaomi-miloco/issues/new/)

### 技术交流讨论

- GitHub 的[讨论区](https://github.com/XiaoMi/xiaomi-miloco/discussions/)

### 加入我们

**Xiaomi Miloco** 团队正在招聘，简历发送至 `xiaomi-miloco@xiaomi.com`，将直达项目负责人。

## 致谢

感谢初代为 Miloco 奋斗的小伙伴们：zhaoy、yangyongjie、xx、Changyu、yyk、junhui、郭兴宝、47、afei。你们的热情与才华，是 Miloco 持续创新、不断前进的根本动力。

特别感谢：
- [llama.cpp](https://github.com/ggml-org/llama.cpp) 开源项目提供推理后端能力
