# Built only after the official compatibility checker passes on the pinned image.
ARG ISAAC_IMAGE
FROM ${ISAAC_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive UV_PYTHON_INSTALL_DIR=/opt/python UV_CACHE_DIR=/opt/uv-cache UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake pkg-config git git-lfs ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY uv /usr/local/bin/uv
ADD isaaclab.tar /opt/IsaacLab/
ADD protomotions.tar /opt/ProtoMotions/
COPY source-revisions.json /opt/studio/source-revisions.json
COPY configure_target.py /opt/studio/configure_target.py
COPY configure_protomotions.py /opt/studio/configure_protomotions.py
COPY verify_dependencies.py /opt/studio/verify_dependencies.py
COPY install_environment.sh /opt/studio/install_environment.sh
ENV ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES
RUN bash /opt/studio/install_environment.sh
ENV PATH=/opt/IsaacLab/.venv/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /opt/IsaacLab
USER 1234:1234
ENTRYPOINT ["/opt/IsaacLab/.venv/bin/python"]
CMD ["--version"]
