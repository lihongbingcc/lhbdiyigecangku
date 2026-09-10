# lhbdiyigecangku

个人第一个 GitHub 仓库 —— 用来存放本地项目（量化交易、Python、爬虫、数据分析等）的远程备份与同步。

## 关于本仓库

- **所有者**: [lihongbingcc](https://github.com/lihongbingcc)
- **可见性**: Public
- **许可证**: Apache License 2.0
- **创建时间**: 2026-09-10

## 同步策略

本地项目目录通过 git remote 关联到本仓库，使用 `git push` 推送到 GitHub 作为远程备份。

## 本地工作流

```
# 1. 首次克隆
git clone https://github.com/lihongbingcc/lhbdiyigecangku.git

# 2. 日常提交
git add .
git commit -m "说明本次改动"
git push -u origin main   # 首次推送；之后只用 git push

# 3. 从其他机器拉取最新版本
git pull
```

## 常用约定

- 中文文件名默认 UTF-8（已配 `i18n.commitEncoding=utf-8`）
- 换行符保留 LF（已配 `core.autocrlf=false`），避免 Windows/Linux 跨平台提交时整个文件被标红
- 长路径支持已开（`core.longpaths=true`），不受 Windows 260 字符路径限制