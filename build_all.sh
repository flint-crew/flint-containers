for i in $(ls Dockerfile-*); do
    docker build --platform linux/amd64 -t alecthomson/flint-containers:${i#Dockerfile-} . -f $i --push
done
