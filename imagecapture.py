import paramiko
import json
import os
import time

import io
from PIL import Image, ImageTk
import tkinter as tk

class CameraSystem:
    def __init__(self, ssh_client, gui_root, config_path='params.json'):
        self.gui_root = gui_root
        self.ssh_client = ssh_client
        self.config_path = config_path
        self.config = self.load_config()

        self.image_frame = tk.Frame(self.gui_root)  # Create a frame to hold image labels
        self.image_frame.grid(row=0, column=0)  # Position the frame
        self.image_index = 0  # Index to track the current image being displayed
        self.images = []  # List to store PhotoImages
        self.image_label = None  # Label to display images
        self.camera_labels = {}  # Dictionary to store camera labels for images

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
    
    def angle_to_steps(self, angle):
        return int(angle * (1/0.18))

    def full_rev_count(self, angle):
        return 360/angle

    def inspect(self):
        folder_with_date = self.config.get("folder_with_date")
        plant_folder = folder_with_date.rsplit('/', 1)[-1] if folder_with_date else 'default_folder'
        stdin,stdout,stderr = self.ssh_client.exec_command(f'sudo mkdir -p /home/pi/Images/{plant_folder}/inspect')

        for camera_id in ['A', 'B', 'C', 'D']:
            if self.config.get(f"camera_{camera_id.lower()}", 0) == 1:
                self.capture_image(plant_folder, self.config.get("plant_name", "Unknown"), self.config.get('Dates', '20240101'), camera_id, 'inspect')
        
        self.fetch_and_display_images(f'/home/pi/Images/{plant_folder}/inspect')

    def imaging(self):
        folder_with_date = self.config.get("folder_with_date")
        plant_folder = folder_with_date.rsplit('/', 1)[-1] if folder_with_date else 'default_folder'
        stdin,stdout,stderr = self.ssh_client.exec_command(f'sudo mkdir -p /home/pi/Images/{plant_folder}/images')

        ANGLE = int(self.config.get("angle"))
        SECONDS = int(self.config.get("seconds"))

        steps = self.angle_to_steps(int(ANGLE))
        count = self.full_rev_count(ANGLE)

        j = 0

        while j < count-1:
            time.sleep(SECONDS)

            for camera_id in ['A', 'B', 'C', 'D']:
                if self.config.get(f"camera_{camera_id.lower()}", 0) == 1:
                    self.capture_image(plant_folder, self.config.get("plant_name", "Unknown"), self.config.get('Dates', '20240101')+f'_00{j}', camera_id, 'images')

            j += 1

            cmd = f'python /home/pi/Turntable.py {steps}'
            stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
            print(stdout.read())

        self.transfer_images(plant_folder, 'images')

    def capture_image(self, plant_folder, plant_name, the_time, camera_id, image_folder):
        file_name = f"{plant_name}_Camera_{camera_id}_{the_time}.jpg"
        command = f'sudo i2cset -y 10 0x24 0x24 {self.get_camera_code(camera_id)} \n' \
                  f'libcamera-jpeg --sharpness 2.0 -t 5000 --viewfinder-width 2312 ' \
                  f'--viewfinder-height 1736 --width 4056 --height 3040 --roi 0.28,0.28,0.41,0.41 ' \
                  f'-o {file_name} --exif EXIF.FocalLength=51/10 ' \
                  f'--exif EXIF.FNumber=9/5 --autofocus \n ' \
                  f'sudo mv {file_name} /home/pi/Images/{plant_folder}/{image_folder}'
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        print(f"Camera: {camera_id} imaging done", stdout.read())
        # Store the camera label for the image
        self.camera_labels[file_name] = camera_id

    def get_camera_code(self, camera_id):
        camera_codes = {'A': '0x32', 'B': '0x22', 'C': '0x12', 'D': '0x02'}
        return camera_codes.get(camera_id, '0x32')
    
    def fetch_and_display_images(self, image_directory):
        raw_images = []
        try:
            sftp_client = self.ssh_client.open_sftp()
            file_list = sftp_client.listdir(image_directory)
            for file_name in file_list:
                if file_name.endswith(('.png', '.jpg', '.jpeg')):  # Filter for image files
                    file_path = os.path.join(image_directory, file_name)
                    with sftp_client.open(file_path, 'rb') as file_handle:
                        raw_images.append((file_handle.read(), file_name))
        except Exception as e:
            print(f"An error occurred while fetching images: {e}")
        finally:
            sftp_client.close()
        
        # Convert raw image data to PhotoImages and store them
        self.images = [(self.resize_image(img_data), file_name) for img_data, file_name in raw_images]
        self.create_image_window()  # Display images in a new window

    def resize_image(self, image_data):
        max_size = (800, 600)  # Set max size to which images should be resized
        image = Image.open(io.BytesIO(image_data))
        image.thumbnail(max_size, Image.ANTIALIAS)
        return ImageTk.PhotoImage(image)

    def create_image_window(self):
        if not self.images:
            print("No images to display.")
            return
        
        window = tk.Toplevel(self.gui_root)
        window.title("Image Inspection")
        self.image_label = tk.Label(window)
        self.image_label.pack()

        self.camera_info_label = tk.Label(window, text="")
        self.camera_info_label.pack()

        # Navigation buttons
        btn_prev = tk.Button(window, text="<< Previous", command=self.show_previous_image)
        btn_prev.pack(side="left")
        btn_next = tk.Button(window, text="Next >>", command=self.show_next_image)
        btn_next.pack(side="right")

        self.show_image(0)  # Show the first image

    def show_image(self, index):
        if 0 <= index < len(self.images):
            self.image_index = index
            image, file_name = self.images[index]
            self.image_label.config(image=image)  # Update the label with the current image
            camera_id = self.camera_labels.get(file_name, "Unknown")
            self.camera_info_label.config(text=f"Camera: {camera_id}")

    def show_next_image(self):
        if self.image_index < len(self.images) - 1:
            self.show_image(self.image_index + 1)

    def show_previous_image(self):
        if self.image_index > 0:
            self.show_image(self.image_index - 1)

    def transfer_images(self, plant_folder, image_folder):
        local_dir = self.config.get("folder_path", "/default/path")
        remote_dir = f"/home/pi/Images/{plant_folder}"
        pi_hostname = self.config.get("pi_hostname")
        os.system(f"scp -r pi@{pi_hostname}:{remote_dir} {local_dir}")
        print("Images transferred to", local_dir)

# Ensure that the CameraSystem instance is used properly
if __name__ == "__main__":
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('raspberrypi.local', username='pi', password='your_password')  # Use real credentials
    camera_system = CameraSystem(client, tk.Tk())
    camera_system.inspect()
    client.close()