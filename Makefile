BIN_DIR := bin

.PHONY: help build install test vet fmt tidy clean

help:
	@echo "build     build all tools under cmd/ into $(BIN_DIR)/"
	@echo "install   install all tools to go install's GOBIN (default ~/go/bin; override with GOBIN)"
	@echo "test      run unit tests"
	@echo "vet       run static checks"
	@echo "fmt       format the code"
	@echo "tidy      tidy dependencies"
	@echo "clean     clean build artifacts"

build:
	@mkdir -p $(BIN_DIR)
	go build -o $(BIN_DIR)/ ./cmd/...

install:
	go install ./cmd/...

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
