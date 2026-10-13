# 怎么把「知行 ZhiXing」上传到 GitHub

> 说明：本项目已推送到小组的公共仓库，仓库根目录即项目根目录。
> 本文保留下来，供队友在本地继续提交、或需要同步到团队仓库时参考。

## 零、先看这里：源码在哪

项目根目录就是本仓库的根目录，包含以下内容：

```
zhixing-agent/            ← 即仓库根目录
├── config.py
├── tools/  core/  web/
├── server.py  cli.py  demo.py  mcp_server.py
├── test_tools.py  requirements.txt
└── docs/                 ← 本随笔与本文档
```

仓库根目录已放好 `.gitignore`（会忽略 `.env`、Python 缓存、运行时数据），
所以不用担心把 API Key 传上去。

---

## 一、前置检查

| 项目 | 要求 |
|------|------|
| git 已安装 | `git --version` 能输出版本号即可 |
| 提交身份已配置 | `git config --global user.name` / `user.email` 有值 |

如果换了电脑或没配过身份，先补上：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

---

## 二、方案 A：命令行上传（推荐，最稳）

### 第 1 步：拿到团队仓库地址

打开浏览器 → 进入你们**第一次团队作业创建的那个公共仓库** →
点绿色的 `Code` 按钮 → 复制 `HTTPS` 地址，长这样：

```
https://github.com/你们的组织名/仓库名.git
```

### 第 2 步：把仓库克隆到本地

打开 Git Bash（或 PowerShell、CMD 都行），选一个好找的位置，例如桌面：

```bash
cd ~/Desktop
git clone https://github.com/你们的组织名/仓库名.git
```

会生成一个和仓库同名的文件夹。

### 第 3 步：把项目复制进去

把整个项目文件夹复制到刚克隆出来的仓库文件夹里：

```bash
cp -r "/路径/到/zhixing-agent" ~/Desktop/仓库名/
```

> 在 Git Bash 里 Windows 路径要写成 `/c/Users/...` 这种形式。
> 也可以直接用鼠标拖拽复制，效果一样。

复制完确认一下：

```bash
cd ~/Desktop/仓库名
ls
# 应该能看到 zhixing-agent 文件夹，以及原来仓库里的其他文件
```

### 第 4 步：提交并推送

```bash
git add .
git status          # 确认项目文件都被纳入（.env 应该不在列表里）
git commit -m "feat: 新增知行 ZhiXing 智能体（待办/天气/文件/计算，含 Web 界面与 MCP 支持）"
git push
```

`git push` 时如果弹出登录窗口，选择浏览器登录或输入用户名 + Token 即可。

### 第 5 步：验证

刷新 GitHub 仓库页面，应该能看到项目文件。
能读到 `README.md` 就成功了。

---

## 三、方案 B：网页拖拽上传（最简单，不用命令行）

1. 浏览器打开团队仓库页面
2. 点 `Add file` → `Upload files`
3. 把 `zhixing-agent` 文件夹**整个拖进**上传区域
4. 下方填写提交说明，例如「新增知行智能体项目」
5. 点 `Commit changes`

**两个注意点**：

- 网页上传**不会保留空文件夹**（比如 `storage/sessions/`）。
  这不影响运行——`config.py` 启动时会自动创建这些目录。
- 上传前请确认 `storage/` 里没有你想保留的私人数据，也不要上传 `.env`。

---

## 四、提交前自检清单

在项目根目录下执行 `ls -a`，确认这些**该传的**都在：

- [x] `README.md`、`config.py`、`server.py`、`cli.py`、`demo.py`、`mcp_server.py`
- [x] `tools/`（5 个文件）、`core/`（4 个文件）
- [x] `web/index.html`
- [x] `test_tools.py`、`requirements.txt`、`.env.example`、`.gitignore`
- [x] `docs/博客园随笔-知行智能体.md`

确认这些**不该传的**没被传上去：

- [ ] `.env`（含 API Key，必须排除）
- [ ] `__pycache__/`（Python 缓存）
- [ ] `storage/sessions/*.json`（个人对话记录）

`.gitignore` 已经帮你挡住了后三项。如果不放心，执行
`git status --short` 逐个核对文件名再提交。

---

## 五、常见问题

**Q1：`git push` 报 `Authentication failed`？**

GitHub 早就不能用「账号 + 密码」推送了，需要 Personal Access Token：

1. GitHub → 右上角头像 → `Settings` → 左侧最下方 `Developer settings`
2. `Personal access tokens` → `Tokens (classic)` → `Generate new token (classic)`
3. 勾选 `repo` 权限，生成后**立刻复制**（离开页面就再也看不到了）
4. 推送时用户名填 GitHub 用户名，密码位置粘贴这个 Token

**Q2：报 `remote origin already exists`？**

说明本地已经关联过远程仓库，改成：

```bash
git remote set-url origin https://github.com/你们的组织名/仓库名.git
```

**Q3：我的队友先推了代码，我推不上去？**

先拉取再推：

```bash
git pull --rebase
git push
```

**Q4：不小心把 `.env` 推上去了怎么办？**

1. 立刻去模型服务商后台**吊销那个 API Key**（这是最重要的一步）
2. 然后从仓库里移除：`git rm --cached .env && git commit -m "chore: 移除 .env" && git push`

**Q5：作业要求提交到第一次团队作业创建的公共仓库，能单独建新仓库吗？**

作业原文写的是"把代码提交到你们第一次团队作业创建的 GitHub 公共仓库中"。
如果新建独立仓库，**建议同时把代码同步一份到团队仓库**，两边都不落空。
无论用哪种方式，仓库都必须设为 `Public`，否则老师看不到。

---

## 六、上传完成后

1. 复制仓库的网页地址，形如 `https://github.com/<账号>/zhixing-agent`
2. 写进博客园随笔的**第五节「GitHub 链接」**
3. 关于分支名：新仓库默认是 `main`，老仓库可能是 `master`，按实际填。

打完这行字，作业的代码部分就全部完成了。
