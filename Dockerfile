# Multi-stage build for Inkscape MCP Server
FROM python:3.12-slim as base

# Metadata
LABEL maintainer="Sandra Schipal <sandra@sandraschi.dev>"
LABEL description="FastMCP server for professional vector graphics using Inkscape"
LABEL version="1.2.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Inkscape dependencies
    inkscape \
    # Image processing libraries
    libjpeg62-turbo-dev \
    libpng-dev \
    libtiff5-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    # Virtual framebuffer — lets Inkscape (and its GTK extensions) run headlessly
    xvfb \
    # System utilities
    curl \
    git \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with a home directory
RUN groupadd -r -g 1000 inkscape && useradd -r -u 1000 -g inkscape -m -d /home/inkscape inkscape

# Set work directory
WORKDIR /app

# Copy and install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip \
    && pip install . \
    && pip install segno

# Create runtime-writable directories and set ownership
RUN mkdir -p /app/generated_svgs /app/logs /app/data \
    && chown -R inkscape:inkscape /app /home/inkscape
USER inkscape

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import inkscape_mcp; print('Health check passed')" || exit 1

# Default command
CMD ["inkscape-mcp", "--help"]

# --- Development stage ---
FROM base as development

# Switch back to root for development
USER root

# Install development dependencies
RUN pip install -e ".[dev]"

# Install development tools
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch back to non-root user
USER inkscape

# Development command
CMD ["sleep", "infinity"]

# --- Jupyter stage ---
FROM base as jupyter

USER root

# Install Jupyter and kernel
RUN pip install --no-cache-dir \
    jupyter \
    notebook \
    ipykernel \
    ipywidgets

# Register the kernel so notebooks can import inkscape_mcp
RUN python -m ipykernel install --sys-prefix --name inkscape-mcp --display-name "Python (inkscape-mcp)"

# Notebook working directory — created fresh for jupyter stage
RUN mkdir -p /notebooks && chown inkscape:inkscape /notebooks

USER inkscape
WORKDIR /notebooks
ENV HOME=/home/inkscape

EXPOSE 8888

CMD ["jupyter", "notebook", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--ServerApp.token=", \
     "--ServerApp.password=", \
     "--ServerApp.notebook_dir=/notebooks"]

# --- Production stage ---
FROM base as production

# Add version info
ARG VERSION=1.2.0
ENV INKSCAPE_MCP_VERSION=${VERSION}

# Expose port if HTTP server is used
EXPOSE 8000

# Production command with proper signal handling
CMD ["python", "-m", "inkscape_mcp.main"]