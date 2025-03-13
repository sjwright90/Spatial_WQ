# use offical latest nginx image
FROM nginx:latest

# remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# copy the custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/

# expose port 80
EXPOSE 80