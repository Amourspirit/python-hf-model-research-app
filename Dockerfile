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
RUN cat > /usr/local/bin/hf-hub <<'EOF'
#!/usr/bin/env sh
set -e

if [ "$#" -eq 0 ]; then
	exec uv run hf --help
fi

if [ "$1" = "download" ]; then
	has_local="0"
	has_cache="0"
	prev=""

	for arg in "$@"; do
		if [ "$prev" = "--local-dir" ]; then
			has_local="1"
		fi
		if [ "$prev" = "--cache-dir" ]; then
			has_cache="1"
		fi

		case "$arg" in
			--local-dir|--local-dir=*)
				has_local="1"
				;;
			--cache-dir|--cache-dir=*)
				has_cache="1"
				;;
		esac

		prev="$arg"
	done

	if [ "$has_local" = "0" ]; then
		set -- "$@" --local-dir "${HF_SHELL_DOWNLOAD_DIR:-/storage/hf-shell/downloads}"
	fi

	if [ "$has_cache" = "0" ]; then
		set -- "$@" --cache-dir "${HF_SHELL_CACHE_DIR:-/storage/hf-shell/cache}"
	fi
fi

exec uv run hf "$@"
EOF
RUN cat > /usr/local/bin/hf-shell <<'EOF'
#!/usr/bin/env sh
set -e

rc_file="/tmp/hf-shell-rc"

cat > "$rc_file" <<'RC_EOF'
export PATH="/app/.venv/bin:$PATH"
hf() {
	/usr/local/bin/hf-hub "$@"
}
echo "hf-shell ready. Use 'hf ...' for Hugging Face CLI (download defaults local-dir and cache-dir)."
RC_EOF

exec /bin/bash --rcfile "$rc_file" -i
EOF
RUN cat > /usr/local/bin/hf-shell-entrypoint <<'EOF'
#!/usr/bin/env sh
set -e

token_path="${HF_TOKEN_PATH:-/storage/hf-shell/token}"
stored_tokens_path="${HF_STORED_TOKENS_PATH:-${HF_HOME:-/storage/hf-shell}/stored_tokens}"

mkdir -p \
	"${HF_SHELL_DOWNLOAD_DIR:-/storage/hf-shell/downloads}" \
	"${HF_SHELL_CACHE_DIR:-/storage/hf-shell/cache}" \
	"${HF_ASSETS_CACHE:-/storage/hf-shell/assets}" \
	"$(dirname "$token_path")" \
	"$(dirname "$stored_tokens_path")"

if [ -d "$token_path" ]; then
	rmdir "$token_path" 2>/dev/null || {
		echo "Error: $token_path is a non-empty directory; remove it from the host."
		exit 1
	}
fi

if [ -d "$stored_tokens_path" ]; then
	rmdir "$stored_tokens_path" 2>/dev/null || {
		echo "Error: $stored_tokens_path is a non-empty directory; remove it from the host."
		exit 1
	}
fi

touch "$token_path" "$stored_tokens_path"


if [ "$#" -eq 0 ]; then
	exec /usr/local/bin/hf-shell
fi

if [ "$1" = "shell" ]; then
	shift
	exec /usr/local/bin/hf-shell "$@"
fi

if [ "$1" = "hf" ]; then
	shift
	exec /usr/local/bin/hf-hub "$@"
fi

exec "$@"
EOF
RUN chmod +x /usr/local/bin/hf-hub /usr/local/bin/hf-shell /usr/local/bin/hf-shell-entrypoint
ENTRYPOINT ["uv", "run", "hf-exporter"]
