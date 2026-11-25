import cv2
import onnxruntime as onnx
import requests
import numpy
from pathlib import Path
import time

# ESP32 URL
URL = "http://10.13.29.77"
AWB = True

# motagem da camera 
esp32_cam = cv2.VideoCapture(URL + ":81/stream")

# função que define a resoloção da imagem
def set_resolution(url: str, index: int=1, verbose: bool=False):
    try:
        if verbose:
            resolutions = "10: UXGA(1600x1200)\n9: SXGA(1280x1024)\n8: XGA(1024x768)\n7: SVGA(800x600)\n6: VGA(640x480)\n5: CIF(400x296)\n4: QVGA(320x240)\n3: HQVGA(240x176)\n0: QQVGA(160x120)"
            print("available resolutions\n{}".format(resolutions))

        if index in [10, 9, 8, 7, 6, 5, 4, 3, 0]:
            requests.get(url + "/control?var=framesize&val={}".format(index))
        else:
            print("Wrong index")
    except:
        print("SET_RESOLUTION: something went wrong")

# define a qualidade da imagem
def set_quality(url: str, value: int=1, verbose: bool=False):
    try:
        if value >= 10 and value <=63:
            requests.get(url + "/control?var=quality&val={}".format(value))
    except:
        print("SET_QUALITY: something went wrong")

# define o tempo de exposição da imagem para não saturar o sensor 
def set_awb(url: str, awb: int=1):
    try:
        awb = not awb
        requests.get(url + "/control?var=awb&val={}".format(1 if awb else 0))
    except:
        print("SET_QUALITY: something went wrong")
    return awb

# loop principal 
if __name__ == '__main__':
    set_resolution(URL, index=9)
    cont_frame = 0
    
    while True:
        if esp32_cam.isOpened():
            
            # faz a leitura dos frames da camera 
            ret, frame = esp32_cam.read()

            if ret:
                HEIGHT, WIDTH = frame.shape[:2] # verifica as dimensões da imagem 
                
                cont_frame += 1
                
                # Exibe o frame em tela
                
                cv2.imshow(f"Frame da esp32-cam {HEIGHT} X {WIDTH}", frame)

                # tecla para encerrar o programa
                key = cv2.waitKey(10) & 0xFF

                if key == ord('q'):
                    break
                
                save_path = Path.home() / "Pictures" / "Esp32" / "dataset" / (f"{cont_frame}" + ".jpeg") # cria o caminho para salvar os frames 
                cv2.imwrite(save_path, frame) # salva imagem
                print(save_path)
                
            time.sleep(1) # captura um frame por segundo 

    cv2.destroyAllWindows()
    esp32_cam.release()