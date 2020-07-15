import subprocess
import configparser
from subprocess import Popen, PIPE
from flask import Flask, render_template, redirect, url_for, request, jsonify, Response, send_file
import os
import shutil
import hashlib
import time
from glob import glob

# ----- CONFIGURATION -----

# Constant Variables
OPENVINO_SOURCE = '/opt/intel/openvino/bin/setupvars.sh'
ROS_SOURCE = '/opt/ros/crystal/setup.bash'

# Variables from file
config = configparser.RawConfigParser()
config.read('config.ini')  # Take The parameters from config.ini file
# Reading values from config.ini
workspace = os.path.join(config['workspace']['path'], '')
endpoint = config['cloud']['endpoint']
dashboard_url = config['cloud']['dashboard_url']

# Variables Initialization
dirname = os.path.dirname(os.path.abspath(__file__))
file_input = os.path.join(dirname, 'tmp', '')
if not os.path.exists(file_input):
    os.makedirs(file_input)

aws_folder = workspace + "AWS/"
if not os.path.exists(aws_folder):
    os.makedirs(aws_folder)

driverbehavior_folder = workspace + "DriverBehavior/"
actionrecognition_folder = workspace + "ActionRecognition/"


def shell_communication(cmd):
    # This function allows to execute a bash command
    session = subprocess.Popen(
        [cmd], stdout=PIPE, stderr=PIPE, shell=True, executable="/bin/bash")
    stdout, stderr = session.communicate()
    if stderr:
        raise Exception("Error "+str(stderr))
    return stdout.decode('utf-8')


def shell_communication_parallel(cmds):
    # --- Running in Parallel ---
    # Rosbag
    print(" --- Initializing Driver Management --- ")
    print("Loading Rosbag")
    rosbag = Popen(cmds[0], stdout=None, stderr=None,
                   shell=True, executable="/bin/bash")
    # Driver Actions
    print("Loading Driver Actions")
    driver_actions = Popen(cmds[1], stdout=None, stderr=None,
                           shell=True, executable="/bin/bash")
    # Driver Behaviour
    print("Loading Driver Behaviour")
    driver_behaviour = Popen(cmds[2] + str(driver_actions.pid), stdout=None, stderr=None,
                             shell=True, executable="/bin/bash")

    print(" --- Ready! ---")
    rosbag.wait()
    driver_actions.wait()
    driver_behaviour.wait()


app = Flask(__name__)  # Flask constructor

# Check if there are MDX (MyriadX) or NCS (Neural Compute Stick).
try:
    subprocess.check_output('dmesg | grep Myriad', shell=True)
    myriad = True
except:
    myriad = False
print(' * Myriad Detected: ' + str(myriad))


# Wait until 60 seconds to check if a file exists.
def wait_for_file(file):
    print("Uploading file...")
    time_counter = 0
    while not (os.path.exists(file)):
        time.sleep(1)
        time_counter += 1
        if time_counter > 60:
            break

# ----- Route Definitions -----
@app.route("/", methods=['POST', 'GET'])
def home():
    templateData = {  # Sending the data to the frontend
        'title': "Driver Management",
        'myriad': myriad
    }
    return render_template("driver-management.html", **templateData)


@app.route('/upload_file', methods=['POST', 'GET'])
# Upload the video file selected into a temporal folder (Video Upload Folder in configuration)
def upload_file():
    if request.method == 'POST':
        if request.files:
            file_driver = request.files.get('file', False)
            if file_driver:
                file = request.files["file"]
                file.save(os.path.join(file_input, file.filename))
            # Detect if exists file_actions
            file_actions = request.files.get('file_actions', False)
            if file_actions:
                file = request.files["file_actions"]
                file.save(os.path.join(file_input, file.filename))
            # End check file_actions
        return ''


@app.route('/run_driver_management', methods=['POST', 'GET'])
# This function runs the bash command when the user runs Driver Management Project in the interface.
def run_driver_management():
    if request.method == 'POST':
        json = request.get_json()

        # Rosbag Command
        command_rosbag = ("source " + ROS_SOURCE + " && source " + driverbehavior_folder + "ets_ros2/install/setup.bash && cd " +
                          driverbehavior_folder + " && while true; do ros2 bag play truck.bag; done;") if (json['rosbag'] == "1") else ("")

        # Driver Actions Command
        command_driver_actions = "source " + ROS_SOURCE + " && source " + OPENVINO_SOURCE + \
            " && cd " + actionrecognition_folder + \
            " && python3 action_recognition.py -m_en models/FP32/driver-action-recognition-adas-0002-encoder.xml -m_de models/FP32/driver-action-recognition-adas-0002-decoder.xml -lb driver_actions.txt -d " + \
            json['target_actions']

        if (json['camera_actions'] == "0" and json['file_actions'] != ""):
            command_driver_actions += " -i '" + \
                file_input + json['file_actions'] + "'"
        else:
            if (json['camera_actions'] == "1"):
                if (json['camera'] == "1"):
                    command_driver_actions += " -i /dev/video2"
                else:
                    command_driver_actions += " -i /dev/video0"

        # Show the output in display
        if (json['show_output'] == "0"):
            command_driver_actions += " --no_show"

        # Send Data to AWS
        if (json['send_to_aws'] == "1"):
            command_driver_actions += " -e " + endpoint + " -r " + aws_folder + "root_ca.pem -c " + \
                aws_folder + "certificate.pem.crt -k " + \
                aws_folder + "private.pem.key -t actions/"

        # Driver Behaviour Command
        command_driver_behaviour = "source " + ROS_SOURCE + " && source " + driverbehavior_folder + "ets_ros2/install/setup.bash && source " + OPENVINO_SOURCE + " && source " + driverbehavior_folder + "scripts/setupenv.sh && cd " + driverbehavior_folder + "build/intel64/Release && ./driver_behavior -d " + \
            json['target'] + " -d_hp " + json['target_hp']

        if (json['camera'] == "0"):
            command_driver_behaviour += " -i '" + \
                file_input + json['file'] + "'"
        else:
            command_driver_behaviour += " -i /dev/video0"
        
        if (json['rosbag'] == "1"):
            command_driver_behaviour += " -ros_sim"

        if (json['model'] == "face-detection-adas-0001"):
            if (json['precision'] == "FP16"):
                command_driver_behaviour += " -m $face116"
            else:
                command_driver_behaviour += " -m $face132"
        else:
            if (json['model'] == "face-detection-retail-0004"):
                if (json['precision'] == "FP16"):
                    command_driver_behaviour += " -m $face216"
                else:
                    command_driver_behaviour += " -m $face232"
        
        # Send Data to AWS
        if (json['send_to_aws'] == "1"):
            command_driver_behaviour += " -endpoint " + endpoint + " -rootca " + aws_folder + "root_ca.pem -cert " + \
                aws_folder + "certificate.pem.crt -key " + \
                aws_folder + "private.pem.key -topic drivers/ -clientid NEXCOM_device"

        # Recognition of the Driver
        if (json['recognition'] == "1"):
            command_driver_behaviour += " -d_recognition -fg " + \
                driverbehavior_folder + "scripts/faces_gallery.json"
        # Landmarks Detection
        if (json['landmarks'] == "1"):
            command_driver_behaviour += " -dlib_lm"
        # Headpose Detection
        if (json['head_pose'] == "1"):
            command_driver_behaviour += " -m_hp $hp32"
        # Save the output in a video file
        if (json['save'] == "1"):
            command_driver_behaviour += " -o "
        # Show the output in display
        if (json['show_output'] == "0"):
            command_driver_behaviour += " -no_show "
        # Synchronous / Asynchronous mode
        if (json['async'] == "1"):
            command_driver_behaviour += " -async"
        if (json['no_show_det'] == "1"):
            command_driver_behaviour += " -no_show_det"
        command_driver_behaviour += " -pid_da "

        commands = [command_rosbag, command_driver_actions,
                    command_driver_behaviour]
        if (json['camera'] == "0"):
            wait_for_file(file_input + json['file'])
        if (json['camera_actions'] == "0"):
            wait_for_file(file_input + json['file_actions'])
        print("Running Driver Management")
        shell_communication_parallel(cmds=commands)
        return ("Finish Driver Management")


def killProcess(processes):
    if (type(processes) == list):
        print(" --- Killing Processes --- ")
        for process in processes:
            os.system('pkill -f ' + process)
            print('Procces killed: ' + process)
        print("--- Finish Killing Processes --- ")
        return "The processes were killed correctly!"
    else:
        return "Error trying kill the processes"


@app.route('/stop_driver_management', methods=['POST', 'GET'])
# This function stop the bash command when the user runs Driver Behaviour Project in the interface.
def stop_driver_management():
    processes = [
        # If select "ros" mat be close the proccess of this program too (Because probably is inside the folder "ros2_ws")
        'truck.bag',
        'action_recognition.py',
        'driver_behavior'
    ]
    out = killProcess(processes)
    return jsonify(out=out)


@app.route('/new-driver-management')
def newdriver_management():
    templateData = {  # Sending the data to the frontend
        'title': "New Driver"
    }
    return render_template("new-driver-management.html", **templateData)


@app.route('/create_driver_management', methods=['POST', 'GET'])
# This function allows create a new driver to Driver Behavior.
def create_driver_management():
    if request.method == 'POST':
        out = "The driver couldn't be created"
        if request.files:
            file = request.files["file"]
            # Save the file with the Driver's name and add the same extension
            file.save(os.path.join(driverbehavior_folder + "drivers/",
                                   request.values['driver'] + "." + file.filename.split('.')[-1]))
            # Generating the list with all the drivers
            print("Creating New Driver")
            shell_communication("cd " + driverbehavior_folder +
                                "scripts/ && python3 create_list.py ../drivers/")
            out = "New driver created!"
        return jsonify(out=out)


@app.route('/dashboard')
def dashboard():
    templateData = {  # Sending the data to the frontend
        'title': "Dashboard",
        'dashboard_url': dashboard_url
    }
    return render_template("dashboard.html", **templateData)


@app.route('/drivers')
def drivers():
    drivers_path = driverbehavior_folder + "/drivers/"
    driver_list = [f for f in os.listdir(os.path.join(
        drivers_path)) if os.path.isfile(os.path.join(drivers_path, f))]
    driver_list.sort()  # Order the list by name

    # Copy folder to static/drivers !!!

    templateData = {  # Sending the data to the frontend
        'title': "Drivers",
        'drivers': driver_list,
        'path': os.path.join(drivers_path)
    }
    return render_template("drivers.html", **templateData)


@app.route("/configuration")
def configuration():
    templateData = {  # Sending the data to the frontend
        'title': "Configuration",
        'workspace': workspace
    }
    return render_template("configuration.html", **templateData)


@app.route("/downloads")
def downloads():
    file_exists = False
    file = driverbehavior_folder + 'build/intel64/Release/video_output.avi'
    if (os.path.exists(file)):
        file_exists = True
    templateData = {  # Sending the data to the frontend
        'title': "Downloads",
        'file_exists': file_exists
    }
    return render_template("downloads.html", **templateData)


@app.route('/download_file')
# This function allows download the video output file.
def download_file():
    video_file = driverbehavior_folder + 'build/intel64/Release/video_output.avi'
    return send_file(video_file, as_attachment=True, cache_timeout=0)


@app.route('/delete_file')
# This function allows delete the video output file.
def delete_file():
    video_file = driverbehavior_folder + 'build/intel64/Release/video_output.avi'
    os.remove(video_file)
    return redirect(url_for('downloads'))


@app.route("/cloud-configuration")
def cloud_configuration():
    templateData = {  # Sending the data to the frontend
        'title': "Cloud Configuration",
        'endpoint': endpoint,
        'dashboard_url': dashboard_url
    }
    return render_template("cloud-configuration.html", **templateData)


@app.route('/cloud_config', methods=['POST', 'GET'])
# This functions saves the new configuration in the config.ini file.
def cloud_config():
    if request.method == 'POST':
        out = False
        json = request.get_json()

        config['cloud']['endpoint'] = json['endpoint']
        config['cloud']['dashboard_url'] = json['dashboard_url']

        # Saving variables in config.ini
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
            out = True

        # Variables are updated with the new values.
        global endpoint, dashboard_url
        endpoint = config['cloud']['endpoint']
        dashboard_url = config['cloud']['dashboard_url']

    return jsonify(out=out)


@app.route('/upload_certificates', methods=['POST', 'GET'])
# Upload the video file selected into a temporal folder (Video Upload Folder in configuration)
def upload_certificates():
    out = False
    if request.method == 'POST':
        if request.files:
            # Certificate
            certificate = request.files.get('certificate', False)
            if certificate:
                file = request.files["certificate"]
                file.save(os.path.join(aws_folder, 'certificate.pem.crt'))
            # Private Key
            private_key = request.files.get('private_key', False)
            if private_key:
                file = request.files["private_key"]
                file.save(os.path.join(aws_folder, 'private.pem.key'))
            # RootCA
            root_ca = request.files.get('root_ca', False)
            if root_ca:
                file = request.files["root_ca"]
                file.save(os.path.join(aws_folder, 'root_ca.pem'))
            out = True
    return jsonify(out=out)


@app.route('/check_pass', methods=['POST', 'GET'])
# This function checks the password to enable the edition of the configuration
def check_pass():
    if request.method == 'POST':
        out = False
        json = request.get_json()
        password = hashlib.md5(json['password'].encode())
        if (password.hexdigest() == "9093363f8ee6138f7ba43606fdab7176"):
            out = True
    return jsonify(out=out)


@app.route('/change_config', methods=['POST', 'GET'])
# This functions saves the new configuration in the config.ini file.
def change_config():
    if request.method == 'POST':
        out = False
        json = request.get_json()

        config['workspace']['path'] = json['workspace']

        # Saving variables in config.ini
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
            out = True

        # Variables are updated with the new values.
        global workspace
        # Workspace
        workspace = os.path.join(config['workspace']['path'], '')

    return jsonify(out=out)


app.run()  # Run Flask App
