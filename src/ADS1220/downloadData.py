import serial
import struct
import zlib
import time
import os
import sys
import datetime 

SERIAL_PORT = "/dev/tty.usbmodem144401"
BAUD_RATE = 115200

# PROTOCOL FLAGS
FLAG_EOF      = 0x01
FLAG_NEW_FILE = 0x02
FLAG_ALL_DONE = 0x04

# folder for the files
DOWNLOAD_DIR = "rides"

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
    
rides_dir = os.path.join(application_path, "rides")
os.makedirs(rides_dir, exist_ok=True)

def delete_files():
    conf = input("You sure you want to delete all files: y/n ?\nInput: ")
    if conf.lower() == 'n':
        return
    elif conf.lower() == 'y':
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5) as ser:
                print("Sending DELETE command to PICO...\n")
                ser.write(b'D')
                response = ser.readline().decode('ascii').strip()
                print(f"Pico atbilde: {response}")
        except Exception as e:
            print(f"Error connecting to device: {e}")
    else:
        print("Invalid input.")
        

def download_files():
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5) as ser:
            print(f"Connected to {SERIAL_PORT}. Sending S to start...\n")
            
            ser.write(b'S')
            time.sleep(0.1)
            
            download_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            session_dir = os.path.join(rides_dir, download_time)
            os.makedirs(session_dir, exist_ok=True) #create folder
            
            current_file = None
            expected_chunk_id = 0
            
            print(f"Data will be saved in: {session_dir}")
            
            while True:
                # 1. reading header
                header = ser.read(12)
                if len(header) < 12:
                    print("Error: Serial timeout, header not received!\n")
                    break
                
                # look for first 9 bytes
                br, flags, chunk_id, crc_pico = struct.unpack('<HBHI', header[:9])
                
                # if all files 
                if flags & FLAG_ALL_DONE:
                    print("\nAll files downloaded!")
                    break
                    
                # 2. read payload data for the name
                payload = ser.read(br)
                if len(payload) < br:
                    print("Error: Wrong payload size!\n")
                    break
                
                # A. if file name payload
                if flags & FLAG_NEW_FILE:
                    filename = payload.decode('ascii').strip('\x00')
                    filepath = os.path.join(session_dir, filename)
                    print(f"\n--- STARTING DOWNLOADING: {filename} ---")
                    
                    if current_file:
                        current_file.close()
                    current_file = open(filepath, "wb")
                    expected_chunk_id = 0
                    
                    file_start_time = time.time()
                    last_print_time = file_start_time
                    interval_bytes = 0
                    total_bytes = 0
                    
                    continue
                
                
                # B. if data payload
                crc = zlib.crc32(payload) & 0xFFFFFFFF
            
                if crc != crc_pico:
                    print(f"\n[ERROR] CRC MISMATCH for BLOCK {chunk_id}! (Pico: {crc_pico:08X}, PC: {crc:08X})")
                    break
            
                if chunk_id != expected_chunk_id:
                    print(f"\n[ERROR] WRONG SEQUENCE. WAITED: {expected_chunk_id}, GOT: {chunk_id}")
                    break
                
                if current_file:
                    current_file.write(payload)
                    
                    interval_bytes+=br
                    total_bytes+=br
                    
                    if chunk_id % 10 == 0:
                        current_time = time.time()
                        dt = current_time - last_print_time
                        
                        if dt > 0:
                            speed_kbps = (interval_bytes / 1024) / dt
                            print(f"[{filename}] BLOCK {chunk_id:04d} OK. Speed: {speed_kbps:.1f} KB/s    ", end='\r')
                    
                            last_print_time = current_time
                            interval_bytes = 0
                    
                
                expected_chunk_id += 1
                
                # C. if last block
                if flags & FLAG_EOF:
                    total_time = time.time() - file_start_time
                    avg_speed = (total_bytes / 1024) / total_time if total_time > 0 else 0
                    
                    print(f"\n✓ File {filename} DONE! ({total_bytes / 1024:.1f} KB in {total_time:.2f}s, Avg: {avg_speed:.1f} KB/s)")
                    if current_file:
                        current_file.close()
                        current_file = None

    except Exception as e:
        print(f"SYSTEM ERROR: {e}")

if __name__ == "__main__":
    c = input("S: DOWNLOAD files from PICO\nD: DELETE files from PICO\nInput: ")
    if c.lower() == 's':
        download_files()
    elif c.lower() == 'd':
        delete_files()
    else:
        print("Invalid option!\n")
