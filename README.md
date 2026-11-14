# nixos-sheng

Xiaomi Pad 6S Pro（sheng）的标准 NixOS + U-Boot 移植，提供独立的单系统与 Android/NixOS 双系统产物。
设备支持优先参考 [debian-sheng](https://github.com/ianchb/debian-sheng)，使用 Nix 包和 NixOS 模块集成。

当前验证基线：内核 7.3.0，NixOS 26.11。双系统采用 Android A 槽 / `userdata`、NixOS B 槽 / `linux`。
启动、标准 rebuild、世代回退、双向切换及多项外设已实测；桌面体验、长期待机等仍需验证。
“能构建”“设备被识别”“实际交互成功”在文档中分别记录，不宣称全部功能已对齐 Debian。

An optional [personal KDE single-boot candidate](docs/personal-kde.md) disables
unused magnetic-keyboard and Focus Pen helpers, includes Flatpak and Flathub,
and selects s2idle for further suspend testing. Existing images keep their
accessory defaults. This candidate does not claim to fix the known DWC3 issue.

| 你要做什么 | 从这里开始 |
| --- | --- |
| 接替维护、让其他 agent 接手 | [维护交接](docs/HANDOVER.md)、[agent 工作约定](AGENTS.md) |
| 安装单系统、了解项目实现 | [项目说明](docs/README.md) |
| 安装/维护双系统、切换 Android | [双系统指南](docs/dual-boot.md) |
| 可选 initrd、ext4 上的 tmpfs 根目录 | [启动与持久化说明](docs/initrd-tmpfs.md)、[preservation 样板](examples/tmpfs-root.nix) |
| 查看功能实测范围、笔配对及指纹注意事项 | [外设验证](docs/peripheral-validation.md) |
| 了解本轮移植过程、失败尝试和验证证据 | [2026-11-06～07 移植记录](docs/history/2026-11-06-07.md) |
| 选择下一项工作 | [待办与验收标准](TODO.md) |
| 调试启动、读日志、检查旧脚本 | [开发指南](docs/DEVELOPMENT.md)、[历史排障笔记](docs/bringup-notes.md) |
| 核对 Debian 方案与版本选择 | [Debian 参考策略](docs/debian-reference.md) |

Actions 中 `build` 构建单系统，`build-dual` 构建双系统；修改代码推送到 `main` 会分别触发两条工作流，
手动运行时选择对应工作流。仅文档变更会跳过 push 构建。

刷写前先确认模式：现有 `fastboot-flash`、`flash-uboot` 会写两个 boot 槽，`flash-rootfs` 会擦写
`userdata`，均不能直接用于保留 Android 的双系统安装。双系统请按独立指南操作。
刷写成功提示不保证数据完整；首次启动前请按 [rootfs 校验记录](docs/rootfs-flash-verification.md)
核对实际分区的完整回读和离线文件系统检查。
