# syntax=docker/dockerfile:1.6

FROM golang:1.24 AS builder
WORKDIR /workspace

COPY go.mod go.sum ./
RUN go mod download

COPY . .

ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags "-s -w" -o /out/deploybot-agent ./cmd/deploybot-agent

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /out/deploybot-agent /usr/local/bin/deploybot-agent
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/deploybot-agent"]
