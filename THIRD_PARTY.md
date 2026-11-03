# Third-party components

Original application source follows LICENSE. Dependencies retain their upstream licenses. Release SBOM/provenance identifies exact packages and image layers.

Major components include Vue/Vite (MIT), FastAPI/SQLAlchemy (MIT), PostgreSQL (PostgreSQL License), Nginx (BSD-style), Python (PSF), Argon2 (MIT/Apache-2.0), ffmpeg/ffprobe (the Alpine build's LGPL/GPL configuration), and their dependencies. No third-party media or production credentials are bundled.

Runtime packages come from pinned official base images and Alpine 3.24 repositories. Matching package sources, recipes and license information are available from [Alpine packages](https://pkgs.alpinelinux.org/packages) and [aports](https://gitlab.alpinelinux.org/alpine/aports). `ffprobe -L` exposes its build/license configuration. Preserve corresponding notices when redistributing images.

Fixture media is generated from color frames and sine waves, with no copied film or music content.
