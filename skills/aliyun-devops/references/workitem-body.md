# Work item body

Write the body before every `projex-create-workitem`. Format is MARKDOWN, Chinese only.

## 1. Pick the type

- **Bug**: bug, issue, defect, error, fix, broken, not working, problem, crash, 缺陷.
- **Story**: story, feature, as a user, new, add, implement, improve, enhancement, 需求.

If the request is both (e.g. "the form is broken AND we should redesign it"), ask which one to file first.

## 2. Ask for missing details

Ask only for what the request does not already give.

- **Bug**: what the user was trying to do; what happened (repro steps 1-3); what should happen; severity (blocks work or cosmetic); browser/OS/version.
- **Story**: role; need; benefit; at least 2-3 acceptance criteria; priority (低/中/高/紧急).

## 3. Fill the template

Replace every placeholder with real content. Never output a template with blank placeholders: ask instead.

- Bug: mark exactly one 严重级别 box and exactly one 影响范围 box with `[x]`.
- Story: write exactly one priority word under 优先级. Leave the 完成定义 boxes unchecked, and name the concrete tests in the testing line.

Show the filled body as a fenced markdown block, then confirm the create (SKILL.md rule 4).

## Bug template

```markdown
## 标题
[简要描述]

## 描述
[问题简述]

## 重现步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

## 预期结果
[应该发生什么]

## 实际结果
[实际发生了什么]

## 优先级

### 严重级别
- [ ] 关键
- [ ] 高
- [ ] 中
- [ ] 低

### 影响范围
- [ ] 生产用户
- [ ] 许多用户
- [ ] 部分用户
- [ ] 最小

## 环境
**操作系统：**
**浏览器：**
**版本：**
```

## Story template

```markdown
## 用户故事
- 作为：[角色]
- 我想要：[功能]
- 以便：[收益]

## 验收标准
- [ ] AC1：[标准]
- [ ] AC2：[标准]
- [ ] AC3：[标准]

## 优先级
[低 / 中 / 高 / 紧急，只写一个]

## 完成定义
- [ ] 所有验收标准已满足
- [ ] 代码已审查
- [ ] 测试已编写并通过（[具体测试，如 XxxTest、Playwright 用例]）
- [ ] 文档已更新
- [ ] 已部署到开发环境
- [ ] QA 已验证
```
