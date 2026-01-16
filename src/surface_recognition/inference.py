from .models import *
from config import *

class InferenceEngine:
    def __init__(self):
        self.device = torch.device("cpu")

        # モデルの構築
        self.model = ResNet18(num_classes=NUM_CLASSES)
        
        # 重みのロード
        try:
            state_dict = torch.load(MODEL_PATH, map_location=self.device)
            self.model.load_state_dict(state_dict)
            print("Model loaded successfully.")
        except FileNotFoundError:
            print(f"Warning: Model file not found at {MODEL_PATH}. Prediction will be random.")
        except Exception as e:
            print(f"Error loading model: {e}")

        self.model.to(self.device)
        self.model.eval() # 推論モードに設定

    def predict(self, audio_buffer):
        """
        Numpyの音声データを受け取り、予測ラベルと確信度を返す
        """
        # 前処理 (PCEN)
        feature = extract_pcen(audio_buffer)
        
        input_tensor = torch.tensor(feature, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        input_tensor = input_tensor.to(self.device)

        with torch.no_grad():
            outputs = self.model(input_tensor)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)
            
            # 最大値とそのインデックスを取得
            confidence, predicted_idx = torch.max(probabilities, 1)
            
            label_idx = predicted_idx.item()
            conf_val = confidence.item()

            label_name = CLASS_LABELS[label_idx] if label_idx < len(CLASS_LABELS) else "Unknown"
            
            return label_name, conf_val