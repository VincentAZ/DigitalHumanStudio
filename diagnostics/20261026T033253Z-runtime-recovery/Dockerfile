FROM sha256:e76a9e93412d46b7f4dcf429d98db5784d4fcbcac4185e8435c0297e048e9d77
ENV UV_HTTP_TIMEOUT=300 UV_HTTP_RETRIES=3 UV_CONCURRENT_DOWNLOADS=4
COPY finish_environment.sh /opt/studio/finish_environment.sh
RUN cd /opt/IsaacLab && uv sync --locked --python 3.12.13 --extra isaacsim && bash /opt/studio/finish_environment.sh
ENV PATH=/opt/IsaacLab/.venv/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /opt/IsaacLab
USER 1234:1234
ENTRYPOINT ["/opt/IsaacLab/.venv/bin/python"]
CMD ["--version"]
