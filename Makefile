BIN_DIR := bin

.PHONY: help build test vet fmt tidy clean

help:
	@echo "build  编译 cmd/ 下所有工具到 $(BIN_DIR)/"
	@echo "test   运行单元测试"
	@echo "vet    静态检查"
	@echo "fmt    格式化代码"
	@echo "tidy   整理依赖"
	@echo "clean  清理构建产物"

build:
	@mkdir -p $(BIN_DIR)
	go build -o $(BIN_DIR)/ ./cmd/...

test:
	go test ./...

vet:
	go vet ./...

fmt:
	go fmt ./...

tidy:
	go mod tidy

clean:
	rm -rf $(BIN_DIR)
