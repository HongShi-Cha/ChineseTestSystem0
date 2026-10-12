# 国语水平测试系统 - 前端

> **当前状态（第 10 步）**：前端已接回真实后端（Python FastAPI + MySQL），
> 由后端同源托管；`js/main.js` 走 `/api/**` 真实接口，
> `js/main.mock.js` 仍保留为"无后端也能看界面"的纯 Mock 版本。
> 下面「改动摘要」一节记录的是最初做纯展示版时的改动，留作历史说明。

本目录由「对接真实后端 API（Spring Boot）」的前端源码改造而来，**已剥离全部后端依赖**，
所有页面数据均为内置硬编码 Mock 数据，可脱离 Java 后端直接预览界面效果，
方便对接 Python 后端的同事查看页面结构与交互。

## 改动摘要

- 删除所有真实网络请求：`fetch`、`axios`、`$.ajax`、`api.get/post/put/del/upload` 等已全部移除。
- 数据改为内置 Mock：题库、账号、考试记录、统计图表数据均由 `js/main.js` 内置并提供。
- 字段改为 Python 风格下划线命名：`student_no`、`class_name`、`total_score`、
  `finished_at`、`updated_at` 等（原 Java 版为 `studentNo`、`className`、`totalScore` 等），
  页面绑定与渲染代码同步更新，前后一致。
- 交互逻辑保留并本地化：登录/注册、题库分页/搜索/题型筛选/增删改、
  考试模拟评分、交卷生成成绩、历史成绩曲线、管理端统计均在浏览器本地完成。

## 如何预览

1. 方式一：直接双击 `index.html` 用浏览器打开（推荐 Chrome / Edge）。
2. 方式二：在任意静态服务器中访问，例如
   `python -m http.server 8000` 后打开 `http://localhost:8000/`。
3. 无需数据库、无需 Java 后端，打开即可用。

> 提示：前端依赖（Bootstrap / Bootstrap Icons / ECharts）已**全部本地化**到
> `assets/vendor/`，不需要联网，也不依赖任何 CDN，内网与离线环境都能直接用。

## 演示账号

| 身份 | 账号 | 密码 | 说明 |
| --- | --- | --- | --- |
| 学生 | 2024001（张三） | 123456 | 已预置 6 次考试成绩，可看曲线/报告 |
| 学生 | 2024002（李四） | 123456 | 已预置 3 次考试成绩 |
| 学生 | 2024003（王五） | 123456 | 已预置 2 次考试成绩 |
| 管理员 | admin | admin123 | 控制台统计 / 题库管理 / 学生成绩 |

在登录页也可以使用"注册"新增学生账号（学号即登录名），新账号默认没有考试成绩。

## 页面清单

| 页面 | 内容 |
| --- | --- |
| `index.html` | 入口页（学生端 / 管理端） |
| `login.html` | 登录 / 注册 |
| `student/dashboard.html` | 学生端首页：统计卡片、最近成绩 |
| `student/exam.html` | 模拟考试：四道大题、倒计时、模拟录音评分 |
| `student/history.html` | 历史成绩曲线 + 明细表（支持导出 CSV） |
| `student/report.html` | 单场成绩报告（含声韵调详情） |
| `admin/dashboard.html` | 管理控制台：统计卡片、最近动态、各题型得分率 |
| `admin/questions.html` | 题库管理：分页、搜索、题型筛选、增删改、模拟 Excel 导入 |
| `admin/students.html` | 学生成绩管理：按学号/姓名/班级搜索、历次成绩弹窗、完整报告弹窗 |

## Mock 数据与本地存储

- 所有假数据由 `js/main.js` 内置（每个列表页均有 5 条以上示例，题库 24 条）。
- 登录状态、注册账号、题库增删改、新交卷的成绩会保存在浏览器
  `localStorage / sessionStorage`（键名前缀 `pthcs_mock_*`），刷新页面仍可保留。
- 想恢复出厂 Mock 数据：浏览器控制台执行
  `localStorage.clear(); sessionStorage.clear();` 后刷新页面即可。

## 前端依赖（已本地化，第 10 步）

| 库 | 版本 | 本地路径 | 原 CDN 地址 |
| --- | --- | --- | --- |
| Bootstrap | 5.3.0 | `assets/vendor/bootstrap/bootstrap.min.css`、`bootstrap.bundle.min.js` | `https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/` |
| Bootstrap Icons | 1.10.0 | `assets/vendor/bootstrap-icons/bootstrap-icons.css` + `fonts/` | `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/` |
| ECharts | 5.4.3 | `assets/vendor/echarts/echarts.min.js` | `https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/` |

升级步骤：按上表把 `assets/vendor/` 下的文件换成新版本，再全局搜索确认没有残留外链即可。
注意 `bootstrap-icons.css` 是用相对路径 `./fonts/` 找字体文件的，升级时 `fonts/` 要一起换掉。

## 与 Python 后端对接提示

本版的 Mock 字段已按下划线命名约定整理，Python 后端可按同样字段命名返回数据
（如 `student_no`、`total_score`、`finished_at`、`updated_at`、`sections[].detail.shengmu` 等），
页面渲染逻辑无需再做字段映射即可对齐。