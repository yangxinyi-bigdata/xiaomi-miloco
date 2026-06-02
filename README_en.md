# Xiaomi Miloco

**Xiaomi Local Copilot** is a future exploration solution for smart homes. Using Xiaomi Home cameras as the source of visual information and a self-developed LLM as its core, it connects all IoT devices throughout the house. Based on the development paradigm of LLM, it enables users to define various family needs and rules in natural language, achieving broader and more creative smart device integration.

<div align="center">

English | [简体中文](README.md)

</div>

## News

- [2025-11] Xiaomi Miloco Framework Open Source

## Fork Modifications (Compared to Upstream)

This project is a fork of the upstream `XiaoMi/xiaomi-miloco` and includes the following exclusive modifications and optimizations:
1. **Custom Active Time Ranges**: You can now set specific active time ranges for your trigger rules (including cross-day schedules!). The logs will also explain much more clearly why a rule didn't run or exactly where it got stuck.
2. **No More Log Spam**: Optimized how errors are displayed. If the same error keeps happening, it won't flood your log page anymore. Instead, it neatly updates the existing error message with the latest timestamp so you know it's still happening.
3. **More Reliable Execution Logs**: Fixed a minor bug where background tasks occasionally ran "too fast" and lost their status updates. Your execution history is now much more accurate.
4. **Your Settings are Actually Saved**: Fixed annoying issues where your custom configurations could be lost or crash the system after a reboot. Now, all your personal settings and custom prompts are securely saved locally and survive any system updates!
5. **Under-the-hood Upgrade**: Updated core dependencies to keep the system running smoothly and stably.

## Key Features

1. New Interaction Paradigm: Based on the development paradigm of LLM, rule-setting and complex device command control can be completed through natural language interaction.
2. On-Device LLM: The home scene tasks are split into two stages: planning and visual understanding. It provides Xiaomi's self-developed on-device model[Xiaomi MiMo-VL-Miloco-7B](https://github.com/XiaoMi/xiaomi-mimo-vl-miloco)to realize on-device video understanding and ensure family privacy and security.
3. New Use for Visual Data: Using camera data streams as a source of perceptual information, the LLM is used to analyze various home scene events contained in the visual data to respond to user queries.
4. Xiaomi Home Ecosystem: It connects with the Xiaomi Home ecosystem, supports the retrieval and execution of Mi Home devices and scenes, and supports sending customized content for Xiao Home notifications.

    <img src="assets/images/ai_center.jpg" width="60%" />

## Quick Start

### System Requirements

- **Hardware Requirements**
```Plain Text
CPU: x64 architecture
Graphics Card: NVIDIA 30 series and above, 8GB VRAM minimum (recommended 12GB and above)
Storage: Recommended 16GB or more available space (for local model storage)
```

- **Software Requirements**
```Plain Text
Operating System:
  - Linux: x64 architecture, recommended Ubuntu 22.04 and above LTS versions
  - Windows: x64 architecture, recommended Windows 10 and above, requires WSL2 support
  - macOS: Not currently supported
Docker: Version 20.10 and above, requires docker compose support
NVIDIA Driver: NVIDIA driver with CUDA support
NVIDIA Container Toolkit: For Docker GPU support
```

### Install

> **Note**: Please ensure your system meets the above hardware and software requirements. Windows systems need to enter the WSL environment.

**Install with Docker (Recommended)**  

The simplest way to quickly experience this project is via the one-click installation script from the source code:

1. Clone this repository locally and enter the directory:
```bash
git clone https://github.com/yangxinyi-bigdata/xiaomi-miloco.git
cd xiaomi-miloco
```

2. Run the one-click installation script (this will automatically pull the latest Docker image and start the service):
```bash
bash scripts/install.sh
```
> **Tip**: During the installation prompt, select `1. GitHub Packages` as the image source. The script will then automatically pull our exclusively built images under the `ghcr.io/yangxinyi-bigdata/` namespace.

3. (Optional) If you need to pull the backend image manually, you can run:
```bash
docker pull ghcr.io/yangxinyi-bigdata/miloco-backend:latest
```
For detailed installation steps, please refer to the [Docker Deployment Documentation](docs/environment-setup.md).

**Install with source code**  
For source code installation steps, please refer to the [Development Guide](docs/development/developer-setup.md).

## Usage Documentation

Please refer to the [Usage Documentation](docs/usage/README.md).

## Contributing

Please refer to the [Contributing Guide](CONTRIBUTING.md).

## License

For license details, please see [LICENSE.md](LICENSE.md).

**Important Notice**: This project is limited to non-commercial use only. Without written authorization from Xiaomi Corporation, this project may not be used for developing applications, web services, or other forms of software.

## Security Issues

If you discover potential security issues in this project, or believe you may have found a security issue, please notify the [Miloco Team](xiaomi-miloco@xiaomi.com) via our vulnerability reporting email. Please do not create public GitHub Issues.

## Contact Us

### Issue Reporting

For issue reporting, please participate through the following methods:
- Submit a [GitHub Issue](https://github.com/XiaoMi/xiaomi-miloco/issues/new/)

### Technical Discussion

- GitHub [Discussions](https://github.com/XiaoMi/xiaomi-miloco/discussions/)

### Join Us

The **Xiaomi Miloco** team is hiring. Send your resume to `xiaomi-miloco@xiaomi.com`, and it will be delivered directly to the project lead.

## Acknowledgments

Thank you to the original team members who worked hard for Miloco：zhaoy、yangyongjie、xx、Changyu、yyk、junhui、郭兴宝、47、afei。

Your passion and talent are the fundamental driving force behind Miloco's continuous innovation and progress.

Special thanks to:
- The [llama.cpp](https://github.com/ggml-org/llama.cpp) open source project for providing inference backend capabilities
