#!/bin/bash

sudo apt install -y wget

path=/app/DriverBehavior/models

cd $path/FP16
rm head-pose-estimation-adas-0001.bin
rm head-pose-estimation-adas-0001.xml
wget https://download.01.org/openvinotoolkit/2018_R3/open_model_zoo/head-pose-estimation-adas-0001/FP16/head-pose-estimation-adas-0001.bin
wget https://download.01.org/openvinotoolkit/2018_R3/open_model_zoo/head-pose-estimation-adas-0001/FP16/head-pose-estimation-adas-0001.xml

cd $path/FP32
rm head-pose-estimation-adas-0001.bin
rm head-pose-estimation-adas-0001.xml
wget https://download.01.org/openvinotoolkit/2018_R3/open_model_zoo/head-pose-estimation-adas-0001/FP32/head-pose-estimation-adas-0001.bin
wget https://download.01.org/openvinotoolkit/2018_R3/open_model_zoo/head-pose-estimation-adas-0001/FP32/head-pose-estimation-adas-0001.xml

cd /app/UI/
