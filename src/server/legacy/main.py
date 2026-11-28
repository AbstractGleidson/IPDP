import cv2
import onnxruntime as onnx
import requests
import numpy
from pathlib import Path
import time

'''
INFO SECTION
- if you want to monitor raw parameters of ESP32CAM, open the browser and go to http://192.168.x.x/status
- command can be sent through an HTTP get composed in the following way http://192.168.x.x/control?var=VARIABLE_NAME&val=VALUE (check varname and value in status)
'''

# ESP32 URL
URL = "http://10.178.77.110"
AWB = True

# Configurações do Modelo e Câmera
MODEL_PATH = Path(__file__).parent / "models" / "yolov8n.onnx"
IMAGE_SIZE = 320  # Resolução de entrada da YOLO
CONF_THRESHOLD = 0.4  # Limiar de confiança para detecção
HEIGHT = 640
WIDTH = 640
CLASS_INTEREST = {0: "Pessoa"}

# Face recognition and opencv setup
cap = cv2.VideoCapture(URL + ":81/stream")
face_classifier = cv2.CascadeClassifier('haarcascade_frontalface_alt.xml') # insert the full path to haarcascade file if you encounter any problem

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

def set_quality(url: str, value: int=1, verbose: bool=False):
    try:
        if value >= 10 and value <=63:
            requests.get(url + "/control?var=quality&val={}".format(value))
    except:
        print("SET_QUALITY: something went wrong")

def set_awb(url: str, awb: int=1):
    try:
        awb = not awb
        requests.get(url + "/control?var=awb&val={}".format(1 if awb else 0))
    except:
        print("SET_QUALITY: something went wrong")
    return awb

if __name__ == '__main__':
    set_resolution(URL, index=9)
    
    providers = ["CPUExecutionProvider"]  # Força execução na CPU
    
    model_session = onnx.InferenceSession(MODEL_PATH, providers=providers)
    input_name = model_session.get_inputs()[0].name

    while True:
        if cap.isOpened():
            ret, frame = cap.read()

            HEIGHT, WIDTH = frame.shape[:2]
            
            # valores padrões se nenhuma pessoa for detectada
            c_x, c_y = WIDTH // 2, HEIGHT // 2

            # Redimensiona para 320x320 e converte BGR para RGB
            img = cv2.resize(
                frame, (IMAGE_SIZE, IMAGE_SIZE), cv2.INTER_CUBIC
            )
        
            # Normalização [0,1] e adequação de dimensões
            input_tensor = img.astype(numpy.float32) / 255.0
            input_tensor = numpy.transpose(input_tensor, (2, 0, 1))
            input_tensor = numpy.expand_dims(input_tensor, axis=0)

            # Inferência 
            results = model_session.run(None, {input_name: input_tensor})[0]
            predictions = numpy.squeeze(results).T

            boxes = []
            confidences = []
            class_ids = []

            # Fatores de escala para mapear de volta à dimensão original da imagem
            x_factor = WIDTH / IMAGE_SIZE
            y_factor = HEIGHT / IMAGE_SIZE

            # processamendo de boxs
            for prediction in predictions:
                scores = prediction[4:]
                class_id = numpy.argmax(scores)
                max_score = scores[class_id]

                if max_score >= CONF_THRESHOLD and class_id in CLASS_INTEREST:
                    cx, cy, w, h = (
                        prediction[0],
                        prediction[1],
                        prediction[2],
                        prediction[3],
                    )

                    left = int((cx - 0.5 * w) * x_factor)
                    top = int((cy - 0.5 * h) * y_factor)
                    width = int(w * x_factor)
                    height = int(
                        h * y_factor
                    ) 

                    boxes.append([left, top, width, height])
                    confidences.append(float(max_score))
                    class_ids.append(class_id)

            # Aplicação de NMS (Non-Maximum Suppression)
            indices = cv2.dnn.NMSBoxes(
                boxes, confidences, CONF_THRESHOLD, 0.45
            )

            array_x, array_y, array_w, array_h = [], [], [], []

            if len(indices) > 0:
                for detection in indices.flatten():
                    array_x.append(min(boxes[detection][0], WIDTH))
                    array_y.append(min(boxes[detection][1], HEIGHT))
                    array_w.append(min(boxes[detection][2], WIDTH))
                    array_h.append(min(boxes[detection][3], HEIGHT))

                min_x, min_y = min(array_x), min(array_y)
                max_x = min(max(array_w) + max(array_x), WIDTH)
                max_y = min(max(array_h) + max(array_y), HEIGHT)

                w = numpy.sqrt(numpy.pow(max_x - min_x, 2))
                h = numpy.sqrt(numpy.pow(max_y - min_y, 2))

                # Atualiza o centro com base nas detecções
                c_x = int(min_x + (w // 2))
                c_y = int(min_y + (h // 2))

                # Desenha o retângulo na área de interesse
                cv2.rectangle(
                    frame, (min_x, min_y), (max_x, max_y), (0, 255, 0), 2
                )
                cv2.circle(frame, (c_x, c_y), 5, (0, 0, 255), -1)
                cv2.putText(
                    frame,
                    f"center: ({c_x},{c_y})",
                    (c_x, c_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    2,
                )

            error_x = c_x - (WIDTH // 2)
            error_y = c_y - (HEIGHT // 2)

            # Exibe o frame em tela
            cv2.imshow("Teste - YOLOv8 ONNX (esp32)", frame)

            key = cv2.waitKey(10) & 0xFF

            if key == ord('q'):
                break
            
            elif key == ord("s"):
                save_path = Path.home() / "Pictures" / "Esp32" / (f"{time.time()}" + ".jpeg")
                cv2.imwrite(save_path, frame)
                print(save_path)

    cv2.destroyAllWindows()
    cap.release()