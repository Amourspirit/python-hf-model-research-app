FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml README.md ./
RUN uv sync --no-dev
COPY src/ src/
RUN cat > /usr/local/bin/hf <<'EOF'
#!/usr/bin/env sh
set -e

has_output="0"
fmt="csv"
expect_output="0"
expect_fmt="0"

for arg in "$@"; do
	if [ "$expect_output" = "1" ]; then
		has_output="1"
		expect_output="0"
		continue
	fi

	if [ "$expect_fmt" = "1" ]; then
		fmt="$arg"
		expect_fmt="0"
		continue
	fi

	case "$arg" in
		--output)
			expect_output="1"
			;;
		--output=*)
			has_output="1"
			;;
		--fmt)
			expect_fmt="1"
			;;
		--fmt=*)
			fmt="${arg#--fmt=}"
			;;
	esac
done

fmt="$(printf '%s' "$fmt" | tr '[:upper:]' '[:lower:]')"

if [ "$has_output" = "1" ]; then
	exec uv run hf-exporter "$@"
fi

if [ "$fmt" = "json" ]; then
	default_output="/output/models.json"
else
	default_output="/output/models.csv"
fi

exec uv run hf-exporter "$@" --output "$default_output"
EOF
RUN chmod +x /usr/local/bin/hf
ENTRYPOINT ["uv", "run", "hf-exporter"]
