FROM python:3.12.11-slim-bookworm

ARG NODE_VERSION=24.18.0
ARG PNPM_VERSION=11.21.0
ARG UV_VERSION=0.12.0
ARG AZURE_CLI_VERSION=2.88.0
ARG BICEP_VERSION=0.46.1
ARG DATABRICKS_CLI_VERSION=1.12.1
ARG DOTNET_SDK_VERSION=10.0.100
ARG SQLPACKAGE_VERSION=170.4.83
ARG M365_ATK_VERSION=1.1.11
ARG M365_PLAYGROUND_VERSION=0.2.27

ENV DEBIAN_FRONTEND=noninteractive
ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="/usr/share/dotnet:/usr/local/bin:/root/.local/bin:${PATH}"
ENV AZURE_BICEP_USE_BINARY_FROM_PATH=true
ENV UV_NO_UPDATE_CHECK=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        apt-transport-https bash build-essential ca-certificates curl git gnupg jq \
        libicu72 libssl3 lsb-release openssh-client procps tar unzip xz-utils zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings \
    && curl -sLS https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor | tee /etc/apt/keyrings/microsoft.gpg >/dev/null \
    && chmod go+r /etc/apt/keyrings/microsoft.gpg \
    && AZ_DIST="$(lsb_release -cs)" \
    && ARCH="$(dpkg --print-architecture)" \
    && printf '%s\n' \
       "Types: deb" \
       "URIs: https://packages.microsoft.com/repos/azure-cli/" \
       "Suites: ${AZ_DIST}" \
       "Components: main" \
       "Architectures: ${ARCH}" \
       "Signed-by: /etc/apt/keyrings/microsoft.gpg" \
       > /etc/apt/sources.list.d/azure-cli.sources \
    && apt-get update \
    && AZ_DEB_VERSION="$(apt-cache madison azure-cli | awk -v v="${AZURE_CLI_VERSION}" '$3 ~ ("^" v) {print $3; exit}')" \
    && test -n "${AZ_DEB_VERSION}" \
    && apt-get install -y --no-install-recommends "azure-cli=${AZ_DEB_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH="$(dpkg --print-architecture)" \
    && case "${ARCH}" in amd64) NODE_ARCH="x64" ;; arm64) NODE_ARCH="arm64" ;; *) exit 1 ;; esac \
    && NODE_FILE="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
    && curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_FILE}" \
    && curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" \
    && grep " ${NODE_FILE}$" SHASUMS256.txt | sha256sum -c - \
    && tar -xJf "${NODE_FILE}" -C /usr/local --strip-components=1 \
    && rm -f "${NODE_FILE}" SHASUMS256.txt

RUN npm install --global \
      "pnpm@${PNPM_VERSION}" \
      "@microsoft/m365agentstoolkit-cli@${M365_ATK_VERSION}" \
      "@microsoft/m365agentsplayground@${M365_PLAYGROUND_VERSION}"

RUN curl --proto '=https' --tlsv1.2 -LsSf \
      "https://releases.astral.sh/github/uv/releases/download/${UV_VERSION}/uv-installer.sh" \
      -o /tmp/uv-installer.sh \
    && UV_INSTALL_DIR=/usr/local/bin sh /tmp/uv-installer.sh \
    && rm -f /tmp/uv-installer.sh

RUN ARCH="$(dpkg --print-architecture)" \
    && case "${ARCH}" in amd64) BICEP_ARCH="x64" ;; arm64) BICEP_ARCH="arm64" ;; *) exit 1 ;; esac \
    && curl -fsSL \
       "https://github.com/Azure/bicep/releases/download/v${BICEP_VERSION}/bicep-linux-${BICEP_ARCH}" \
       -o /usr/local/bin/bicep \
    && chmod +x /usr/local/bin/bicep

RUN ARCH="$(dpkg --print-architecture)" \
    && case "${ARCH}" in amd64) DB_ARCH="amd64" ;; arm64) DB_ARCH="arm64" ;; *) exit 1 ;; esac \
    && DB_FILE="databricks_cli_${DATABRICKS_CLI_VERSION}_linux_${DB_ARCH}.tar.gz" \
    && curl -fsSLO "https://github.com/databricks/cli/releases/download/v${DATABRICKS_CLI_VERSION}/${DB_FILE}" \
    && curl -fsSLO "https://github.com/databricks/cli/releases/download/v${DATABRICKS_CLI_VERSION}/databricks_cli_${DATABRICKS_CLI_VERSION}_SHA256SUMS" \
    && grep " ${DB_FILE}$" "databricks_cli_${DATABRICKS_CLI_VERSION}_SHA256SUMS" | sha256sum -c - \
    && tar -xzf "${DB_FILE}" \
    && install -m 0755 databricks /usr/local/bin/databricks \
    && rm -f "${DB_FILE}" "databricks_cli_${DATABRICKS_CLI_VERSION}_SHA256SUMS" databricks

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --version "${DOTNET_SDK_VERSION}" --install-dir "${DOTNET_ROOT}" --no-path \
    && ln -sf "${DOTNET_ROOT}/dotnet" /usr/local/bin/dotnet \
    && rm -f /tmp/dotnet-install.sh \
    && mkdir -p /opt/sqlpackage \
    && dotnet tool install microsoft.sqlpackage --version "${SQLPACKAGE_VERSION}" --tool-path /opt/sqlpackage \
    && ln -sf /opt/sqlpackage/sqlpackage /usr/local/bin/sqlpackage

RUN groupadd --gid 1000 vscode \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash vscode \
    && mkdir -p /workspaces/TechScope \
    && chown -R vscode:vscode /workspaces

WORKDIR /workspaces/TechScope

RUN python --version \
    && uv --version \
    && node --version \
    && pnpm --version \
    && az --version >/dev/null \
    && bicep --version \
    && databricks -v \
    && sqlpackage /Version \
    && atk -h >/dev/null \
    && npm list -g "@microsoft/m365agentsplayground@${M365_PLAYGROUND_VERSION}" --depth=0 >/dev/null

USER vscode
CMD ["sleep", "infinity"]
