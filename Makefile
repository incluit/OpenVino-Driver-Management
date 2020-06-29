docker-build:
	docker build -t openvino-incluit . --rm

docker-run: 
	docker run --name drivermanagementcont --net=host --env="DISPLAY" -it -d --device /dev/dri:/dev/dri --device-cgroup-rule='c 189:* rmw' -v /dev/bus/usb:/dev/bus/usb --privileged --volume="$$HOME/.Xauthority:/root/.Xauthority:rw" openvino-incluit

docker-start:
	xhost +
	docker start drivermanagementcont
	docker exec -it drivermanagementcont /bin/bash

docker-stop:
	docker stop drivermanagementcont

docker-remove:
	docker stop drivermanagementcont
	docker rm drivermanagementcont
