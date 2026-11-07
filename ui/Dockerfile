# The ui image (§4.7): static files only. nginx-unprivileged runs as uid 101 and nginx.conf
# listens on 8080 and writes only under /tmp (an emptyDir in the Deployment).
FROM nginxinc/nginx-unprivileged:1.27.5-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html

USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
