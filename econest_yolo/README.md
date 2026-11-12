# econest_yolo

Bird detection service for EcoNest. It receives photos over MQTT, processes them with YOLO (frozen weights), and, if it detects a bird, publishes the result (class, confidence, bounding box, and image) for Grafana to consume.

```
camera/sensor --(JPEG)--> econest/camera/image --> [econest_yolo] --(JSON)--> econest/detections --> Grafana
```

If there are no birds in the photo, nothing is published.

## Requirements

- Python 3.10+ (on a Raspberry Pi 5 running 64-bit Raspberry Pi OS)
- An MQTT broker (for example, Mosquitto) accessible from the Raspberry Pi
- YOLO11n weights pretrained on COCO (`yolo11n.pt`), without training or modification

## Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On the Raspberry Pi (aarch64), `pip` installs the PyTorch wheels for ARM directly; inference runs on the CPU.

### YOLO11 weights (COCO)

The pretrained `yolo11n.pt` weights (the "nano" model, the lightest and most suitable for the available hardware) are published by Ultralytics. There are two ways to obtain them:

**Option A: automatic.** When running the service for the first time with `weights: yolo11n.pt`, Ultralytics downloads the weights to the current directory. An Internet connection is required the first time.

**Option B: manual**:

```bash
# From the repository root
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
```

The `.pt` files are listed in `.gitignore` and are not uploaded to the repository. If you store them elsewhere, specify the path in `model.weights`.

COCO has 80 classes; birds are class **14** (`bird`). The service filters for this class, so it ignores people, cars, etc. Pigeons are detected as `bird`.

## Configuration

Copy `config.example.yaml` to `config.yaml` (the real configuration file is listed in `.gitignore`):

```bash
cp config.example.yaml config.yaml
```

Tested `config.yaml` contents:

```yaml
mqtt:
  host: localhost
  port: 1883
  username: null
  password: null
  input_topic: econest/camera/image
  output_topic: econest/detections
model:
  weights: yolo11n.pt   # frozen COCO weights
  conf: 0.25
  classes: [14]         # COCO 14 = bird
  device: cpu
```

Adjust `mqtt.host` (and credentials, if applicable) to match the actual broker. Meaning of each key:

| Key | Default | Description |
|---|---|---|
| `mqtt.host` / `mqtt.port` | `localhost` / `1883` | MQTT broker |
| `mqtt.username` / `mqtt.password` | `null` | Credentials (optional) |
| `mqtt.input_topic` | `econest/camera/image` | Input topic (raw JPEG) |
| `mqtt.output_topic` | `econest/detections` | Output topic (JSON) |
| `model.weights` | `yolo11n.pt` | Path or name of the weights |
| `model.conf` | `0.25` | Confidence threshold |
| `model.classes` | `[14]` | Class IDs to detect (14 = `bird` in COCO) |
| `model.device` | `cpu` | Inference device |

To use custom weights trained on your dataset, change `model.weights` and `model.classes`; no code changes are required.

## Dataset
Example dataset: "https://universe.roboflow.com/wiings/pigeon-mg46t/dataset/1"

It is only used to test inference (not for training): with the frozen YOLOv11 COCO weights, `yolo11n.pt` detects a `bird` in all 74 validation images.

## Usage

Service:

```bash
python -m econest_yolo --config config.yaml
```

Local test with an image, without a broker:

```bash
python scripts/detect_file.py foto.jpg --config config.yaml
```

Test with the broker:

```bash
mosquitto_sub -t econest/detections
mosquitto_pub -t econest/camera/image -f foto.jpg
```

## Message contract

**Input** (`mqtt.input_topic`): the payload is the JPEG itself, in bytes.

**Output** (`mqtt.output_topic`): JSON.

```json
{
  "timestamp": "2026-11-12T10:30:00+00:00",
  "image_width": 640,
  "image_height": 480,
  "detections": [
    {
      "class": "bird",
      "class_id": 14,
      "confidence": 0.87,
      "bbox_xyxy": [120.5, 80.0, 310.2, 260.7]
    }
  ],
  "image_b64": "<original JPEG in base64>"
}
```

- `bbox_xyxy`: `[x1, y1, x2, y2]` in pixels of the original image (top-left and bottom-right corners).
- `timestamp`: UTC, ISO 8601, when the image was processed.
- `image_b64`: the unannotated image; the bounding box is drawn by the consumer.

Input messages that are not valid images are discarded and recorded in the log.

## Structure

| File | Purpose |
|---|---|
| `config.py` | Loads configuration and default values |
| `detector.py` | `BirdDetector`: loads the model once and runs inference |
| `messages.py` | Builds the output JSON |
| `service.py` | MQTT client: subscription, inference, and publishing |
| `__main__.py` | Entry point (`python -m econest_yolo`) |

## Testing

```bash
pytest tests
```
