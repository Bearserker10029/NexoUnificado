| Imagen inicial | Imagen corregida | HIGH+CRIT antes (CRIT) | HIGH+CRIT despues (CRIT) | CVE corregidos | CVE nuevos |
|---|---|---|---|---|---|
| alpine:3.20 | alpine:3.22 | 2 (0) | 0 (0) | 2 | 0 |
| docker:27-cli | docker:28-cli | 121 (8) | 117 (7) | 12 | 8 |
| nginx:1.27-alpine | nginx:1.29-alpine | 70 (3) | 58 (1) | 32 | 20 |
| prom/prometheus:v2.55.1 | prom/prometheus:v3.5.0 | 60 (2) | 56 (2) | 5 | 1 |
| prom/node-exporter:v1.8.2 | prom/node-exporter:v1.9.1 | 52 (1) | 48 (1) | 5 | 1 |
| prom/blackbox-exporter:v0.25.0 | prom/blackbox-exporter:v0.27.0 | 56 (3) | 50 (2) | 6 | 0 |
| grafana/grafana:11.3.0 | grafana/grafana:11.6.0 | 105 (7) | 114 (8) | 11 | 20 |

## CVE CRITICAL (imagen, CVE, paquete, version inicial, correccion, resultado)

| Imagen | CVE | Paquete | Version inicial | Correccion aplicada | Resultado posterior |
|---|---|---|---|---|---|
| docker:27-cli | CVE-2025-68121 | stdlib | v1.22.10 | docker:27-cli -> docker:28-cli (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) | Persiste (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) |
| docker:27-cli | CVE-2026-111497 | brotli-libs | 1.1.0-r2 | docker:27-cli -> docker:28-cli (parche: 1.1.1-r0) | Corregida |
| docker:27-cli | CVE-2026-123158 | openssh-client-common | 9.9_p1-r2 | docker:27-cli -> docker:28-cli (parche: 9.9_p2-r1) | Persiste (parche: 10.0_p1-r11) |
| docker:27-cli | CVE-2026-123158 | openssh-client-default | 9.9_p1-r2 | docker:27-cli -> docker:28-cli (parche: 9.9_p2-r1) | Persiste (parche: 10.0_p1-r11) |
| docker:27-cli | CVE-2026-123158 | openssh-keygen | 9.9_p1-r2 | docker:27-cli -> docker:28-cli (parche: 9.9_p2-r1) | Persiste (parche: 10.0_p1-r11) |
| docker:27-cli | CVE-2026-31789 | libcrypto3 | 3.3.3-r0 | docker:27-cli -> docker:28-cli (parche: 3.3.7-r0) | Persiste (parche: 3.5.6-r0) |
| docker:27-cli | CVE-2026-31789 | libssl3 | 3.3.3-r0 | docker:27-cli -> docker:28-cli (parche: 3.3.7-r0) | Persiste (parche: 3.5.6-r0) |
| docker:27-cli | CVE-2026-33186 | google.golang.org/grpc | v1.68.1 | docker:27-cli -> docker:28-cli (parche: 1.79.3) | Persiste (parche: 1.79.3) |
| nginx:1.27-alpine | CVE-2026-111497 | brotli-libs | 1.1.0-r2 | nginx:1.27-alpine -> nginx:1.29-alpine (parche: 1.1.1-r0) | Persiste (parche: 1.2.1-r0) |
| nginx:1.27-alpine | CVE-2026-31789 | libcrypto3 | 3.3.3-r0 | nginx:1.27-alpine -> nginx:1.29-alpine (parche: 3.3.7-r0) | Corregida |
| nginx:1.27-alpine | CVE-2026-31789 | libssl3 | 3.3.3-r0 | nginx:1.27-alpine -> nginx:1.29-alpine (parche: 3.3.7-r0) | Corregida |
| prom/prometheus:v2.55.1 | CVE-2025-68121 | stdlib | v1.23.2 | prom/prometheus:v2.55.1 -> prom/prometheus:v3.5.0 (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) | Persiste (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) |
| prom/prometheus:v2.55.1 | CVE-2026-33186 | google.golang.org/grpc | v1.66.0 | prom/prometheus:v2.55.1 -> prom/prometheus:v3.5.0 (parche: 1.79.3) | Persiste (parche: 1.79.3) |
| prom/node-exporter:v1.8.2 | CVE-2025-68121 | stdlib | v1.22.5 | prom/node-exporter:v1.8.2 -> prom/node-exporter:v1.9.1 (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) | Persiste (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) |
| prom/blackbox-exporter:v0.25.0 | CVE-2024-24790 | stdlib | v1.22.2 | prom/blackbox-exporter:v0.25.0 -> prom/blackbox-exporter:v0.27.0 (parche: 1.21.11, 1.22.4) | Corregida |
| prom/blackbox-exporter:v0.25.0 | CVE-2025-68121 | stdlib | v1.22.2 | prom/blackbox-exporter:v0.25.0 -> prom/blackbox-exporter:v0.27.0 (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) | Persiste (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) |
| prom/blackbox-exporter:v0.25.0 | CVE-2026-33186 | google.golang.org/grpc | v1.63.2 | prom/blackbox-exporter:v0.25.0 -> prom/blackbox-exporter:v0.27.0 (parche: 1.79.3) | Persiste (parche: 1.79.3) |
| grafana/grafana:11.3.0 | CVE-2025-68121 | stdlib | v1.23.1 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) | Persiste (parche: 1.24.13, 1.25.7, 1.26.0-rc.3) |
| grafana/grafana:11.3.0 | CVE-2026-31789 | libcrypto3 | 3.3.2-r0 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 3.3.7-r0) | Persiste (parche: 3.3.7-r0) |
| grafana/grafana:11.3.0 | CVE-2026-31789 | libssl3 | 3.3.2-r0 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 3.3.7-r0) | Persiste (parche: 3.3.7-r0) |
| grafana/grafana:11.3.0 | CVE-2026-33186 | google.golang.org/grpc | v1.66.0 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 1.79.3) | Persiste (parche: 1.79.3) |
| grafana/grafana:11.3.0 | CVE-2026-33815 | github.com/jackc/pgx/v5 | v5.5.5 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 5.9.0) | Persiste (parche: 5.9.0) |
| grafana/grafana:11.3.0 | CVE-2026-33816 | github.com/jackc/pgx/v5 | v5.5.5 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 5.9.0) | Persiste (parche: 5.9.0) |
| grafana/grafana:11.3.0 | GHSA-r277-6w6q-xmqw | github.com/getkin/kin-openapi | v0.125.0 | grafana/grafana:11.3.0 -> grafana/grafana:11.6.0 (parche: 0.144.0) | Persiste (parche: 0.144.0) |
