docker build -t $DOCKER_USER/$CLIENT_IMAGE_NAME .
docker tag $DOCKER_USER/$CLIENT_IMAGE_NAME $DOCKER_USER/$CLIENT_IMAGE_NAME:$CLIENT_VER
docker push $DOCKER_USER/$CLIENT_IMAGE_NAME:$CLIENT_VER