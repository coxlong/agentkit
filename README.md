# agentkit

给 agent 使用的命令行小工具集合（如对象存储操作），单 Go 模块、多命令结构。

## 结构

```
cmd/<tool>/main.go   # 每个小工具一个独立 main 包，编译产物为同名二进制
internal/...         # 各工具共享的内部包（如对象存储 client），不对外暴露
```

## 开发

```bash
make build   # 编译 cmd/ 下所有工具到 bin/
make test
make vet
```

新增一个工具：创建 `cmd/<tool>/main.go`，用 cobra 定义命令即可。共享逻辑放 `internal/`，
需要访问对象存储等外部服务的凭据统一走环境变量，不要写入代码或仓库。
