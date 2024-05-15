import paramiko
import json
import os

class CameraSystem:
    def __init__(self, ssh_client, config_path='params.json'):
        self.ssh_client = ssh_client
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Configuration file not found.")
            return {}
        except json.JSONDecodeError:
            print("Error decoding JSON from the configuration file.")
            return {}

    def inspect(self):
        folder_with_date = self.config.get("folderWithDate_path")
        plant_folder = folder_with_date.rsplit('/', 1)[-1] if folder_with_date else 'default_folder'

        for camera_id in ['A', 'B', 'C', 'D']:
            if self.config.get(f"camera_{camera_id.lower()}", 0) == 1:
                self.capture_image(plant_folder, self.config.get("plant_name", "Unknown"), self.config.get('Dates', '20240101'), camera_id)

        self.transfer_images(plant_folder)

    def capture_image(self, plant_folder, plant_name, the_time, camera_id):
        command = f'sudo i2cset -y 10 0x24 0x24 {self.get_camera_code(camera_id)} \n' \
                  f'libcamera-jpeg --sharpness 2.0 -t 5000 --viewfinder-width 2312 ' \
                  f'--viewfinder-height 1736 --width 4056 --height 3040 --roi 0.28,0.28,0.41,0.41 ' \
                  f'-o {plant_name}_Camera_{camera_id}_{the_time}.jpg --exif EXIF.FocalLength=51/10 ' \
                  f'--exif EXIF.FNumber=9/5 --autofocus \n ' \
                  f'sudo mv {plant_name}_Camera_{camera_id}_{the_time}.jpg /home/pi/Images/{plant_folder}/inspect'
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        print(f"Camera: {camera_id} imaging done", stdout.read())

    def get_camera_code(self, camera_id):
        camera_codes = {'A': '0x32', 'B': '0x22', 'C': '0x12', 'D': '0x02'}
        return camera_codes.get(camera_id, '0x32')

    def transfer_images(self, plant_folder):
        local_dir = self.config.get("folder_path", "/default/path")
        remote_dir = f"/home/pi/Images/{plant_folder}/inspect"
        os.system(f"scp -r pi@raspberrypi.local:{remote_dir} {local_dir}")
        print("Images transferred to", local_dir)

# Ensure that the CameraSystem instance is used properly
if __name__ == "__main__":
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('raspberrypi.local', username='pi', password='your_password')  # Use real credentials
    camera_system = CameraSystem(client)
    camera_system.inspect()
    client.close()