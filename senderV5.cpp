#include <SPI.h>
#include <LoRa.h>

// =================================================================
// 測試載波頻率配置（請依據當下測試配置切換註解，再進行燒錄）
// =================================================================
//#define LORA_FREQ   433E6   // 433 MHz 鏈路：配置 3 & 配置 4
#define LORA_FREQ      915E6   // 915 MHz 鏈路：配置 1 & 配置 2

// =================================================================
// ESP32 硬體腳位配置（發射端 Orion v5/v6 自訂 SPI 腳位）
// =================================================================
#define SCK_PIN   18
#define MISO_PIN  19
#define MOSI_PIN  23
#define NSS_PIN   33   // CS 片選
#define RST_PIN   26   // Reset
#define DIO0_PIN  13   // 中斷腳位

enum Mode { IDLE, PRE_TEST, FORMAL_TEST, STRESS_TEST };
Mode currentMode = IDLE;
int currentSF = 7;
unsigned long testInterval = 500; 
unsigned long packetCounter = 0;
unsigned long lastSendTime = 0;
const int packetLimit = 100;
int targetPayloadLength = 255; // 目標封包長度 (SX1276 極限為 255)
String currentUUID = "N/A";    // 儲存當前測試的 UUID

void handleSerial();
void sendPacket();
void updateParams(int sf);
void printMenu();
unsigned long getSafeInterval(int sf); 

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000); // 針對具備 Native USB 的型號提供保護
  delay(500); // 確保 Serial 硬體與主機端連線穩定
  while (Serial.available() > 0) {
    Serial.read(); // 清除開機時產生的雜訊與快取殘留數據
  }
  Serial.setTimeout(50); // 縮短超時時間，避免雜訊導致 loop 長時間阻塞
  
  // 顯示當前燒錄的頻率參數，提供測試人員現場核對
  Serial.print("\n=== LoRa 發射端初始化 [頻率: ");
  Serial.print(LORA_FREQ / 1E6);
  Serial.println(" MHz] ===");

  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, NSS_PIN);
  LoRa.setPins(NSS_PIN , RST_PIN, DIO0_PIN);
  
  if (!LoRa.begin(LORA_FREQ)) { 
    Serial.println("LoRa 初始化失敗，請確認接線與頻率設定！"); 
    while(1); 
  }
  
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(6);
  LoRa.setPreambleLength(12);
  LoRa.setSyncWord(0xF1);
  LoRa.enableCrc();      // 【盲點修復】開啟硬體 CRC 避免接收端收到損壞封包
  LoRa.setTxPower(20);   // 【盲點修復】強制設定為最大 20dBm 功率，穩定長距測試基線
  //LoRa.setTxPower(-30);
  printMenu();
}

void loop() {
  handleSerial();

  if (currentMode != IDLE) {
    // 檢查是否達到發送間隔
    if (millis() - lastSendTime > testInterval) {
      sendPacket();
      
      // 更新發射時間基準點，確保 testInterval 是純粹的間隔冷卻時間
      lastSendTime = millis(); 

      // 檢查是否達到單次測試 100 包的上限
      if ((currentMode == FORMAL_TEST || currentMode == STRESS_TEST) && packetCounter >= packetLimit) {
        Serial.println("\n>>> 測試任務完成，回到待機。");
        currentMode = IDLE;
        printMenu();
      }
    }
  }
}

void handleSerial() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    String lowerInput = input;
    lowerInput.toLowerCase(); 
    
    if (lowerInput == "p" || lowerInput.startsWith("p ")) {
      int sf = 7;
      if (lowerInput.startsWith("p ")) {
        if (sscanf(lowerInput.c_str(), "p %d", &sf) != 1 || sf < 6 || sf > 12) {
            sf = 7;
        }
      }
      currentMode = PRE_TEST;
      testInterval = 1000;
      updateParams(sf);
      Serial.print("\n>>> [環境預測量階段] SF"); Serial.print(sf); Serial.println(", Interval 1s");
      lastSendTime = millis() - testInterval; 
      
    } else if (lowerInput == "x") {
      currentMode = IDLE;
      Serial.println("\n>>> 已停止。");
      
    } else if (lowerInput.startsWith("u ")) {
      currentUUID = input.substring(2);
      currentUUID.trim();
      Serial.print("\n>>> [設定] UUID 已更改為: ");
      Serial.println(currentUUID);
      
    } else if (lowerInput.startsWith("s ")) {
      // 使用 sscanf 解析字串，防呆設計，避免使用者輸入錯誤格式導致崩潰
      int sf = 0, inter = 0;
      if (sscanf(lowerInput.c_str(), "s %d %d", &sf, &inter) == 2) {
            
        if (sf >= 6 && sf <= 12 && inter > 0) {
          currentMode = STRESS_TEST;
          testInterval = inter;
          updateParams(sf);
          Serial.print("\n>>> [極限壓力測試] SF"); Serial.print(sf);
          Serial.print(", Interval "); Serial.print(inter); Serial.println("ms");
          lastSendTime = millis() - testInterval; 
        } else {
          Serial.println(">>> 參數錯誤：SF 需介於 6-12，Interval 需 > 0");
        }
      } else {
        Serial.println(">>> 格式錯誤：請使用 s [SF] [Interval] (例如 s 7 150)");
      }
      
    } else if (lowerInput.startsWith("l ")) {
      int len = 0;
      if (sscanf(lowerInput.c_str(), "l %d", &len) == 1) {
            
        if (len >= 10 && len <= 255) { // 修改上限至 255
          targetPayloadLength = len;
          Serial.print("\n>>> [設定] 目標封包長度已更改為: "); 
          Serial.print(targetPayloadLength); Serial.println(" Bytes");
        } else {
          Serial.println(">>> 參數錯誤：長度需介於 10 到 255 Bytes 之間");
        }
      } else {
        Serial.println(">>> 格式錯誤：請使用 l [長度] (例如 l 255)");
      }
      
    } else if (lowerInput.startsWith("f ")) {
      long freq = 0;
      if (sscanf(lowerInput.c_str(), "f %ld", &freq) == 1) {
        LoRa.idle();
        LoRa.setFrequency(freq);
        Serial.print("+SET_OK: Freq="); 
        Serial.print(freq / 1E6); Serial.println("MHz");
      }
    } else if (lowerInput.startsWith("b ")) {
      long bw = 0;
      if (sscanf(lowerInput.c_str(), "b %ld", &bw) == 1) {
        LoRa.idle();
        LoRa.setSignalBandwidth(bw);
        Serial.print("+SET_OK: BW="); 
        Serial.println(bw);
      }
    } else if (lowerInput.startsWith("c ")) {
      int cr = 0;
      if (sscanf(lowerInput.c_str(), "c %d", &cr) == 1) {
        LoRa.idle();
        LoRa.setCodingRate4(cr);
        Serial.print("+SET_OK: CR=4/"); 
        Serial.println(cr);
      }
    } else if (lowerInput.startsWith("v ")) {
      int sf = 0;
      if (sscanf(lowerInput.c_str(), "v %d", &sf) == 1) {
        if (sf >= 6 && sf <= 12) {
          updateParams(sf);
          Serial.print("+SET_OK: SF="); 
          Serial.println(sf);
        }
      }
    } else {
      int sf = input.toInt();
      if (sf >= 6 && sf <= 12) {
        currentMode = FORMAL_TEST;
        updateParams(sf);
        testInterval = getSafeInterval(sf);
        Serial.print("\n>>> [正式測試階段] SF"); Serial.print(sf);
        Serial.print(", Interval "); Serial.print(testInterval); Serial.println("ms");
        lastSendTime = millis() - testInterval; 
      }
    }
  }
}

void updateParams(int sf) {
  currentSF = sf;
  packetCounter = 0;
  LoRa.idle();
  LoRa.setSpreadingFactor(sf);
}

void sendPacket() {
  unsigned long start = millis();
  
  // 組裝基礎通訊訊息
  String payload = "";
  if (currentMode == PRE_TEST) payload += "TST:";
  else if (currentMode == STRESS_TEST) payload += "STR:";
  else payload += "FRM:";
  
  payload += String(packetCounter);
  payload += ":";
  payload += currentUUID;

  // 動態向後填充星號，直到滿足 256 位元組長度限制
  while (payload.length() < (size_t)targetPayloadLength) {
    payload += "*"; 
  }

  // 封包實際發射
  if (currentSF == 6) {
    LoRa.beginPacket(true); // Implicit header (SF6 必須)
  } else {
    LoRa.beginPacket();
  }
  LoRa.print(payload);
  LoRa.endPacket(); 
  unsigned long duration = millis() - start;

  Serial.print(currentMode == PRE_TEST ? "[PRE]" : (currentMode == STRESS_TEST ? "[STRESS]" : "[FORM]"));
  Serial.print(" SF"); Serial.print(currentSF);
  Serial.print(" | ID:"); Serial.print(packetCounter);
  Serial.print(" | UUID:"); Serial.print(currentUUID);
  Serial.print(" | Len:"); Serial.print(payload.length()); 
  Serial.print(" | ToA:"); Serial.print(duration); Serial.println("ms");
  
  packetCounter++;
}

unsigned long getSafeInterval(int sf) {
  if (sf <= 7) return 250;
  if (sf == 8) return 500;
  if (sf == 9) return 1000;
  if (sf == 10) return 2000;
  return 5000; // 高擴頻因子給予較長的冷卻時間，防止干擾與擁塞
}

void printMenu() {
  Serial.println("\n--- 控制指令 ---");
  Serial.println("  f [Hz]     : 設定頻率 (例如 f 915000000)");
  Serial.println("  b [Hz]     : 設定頻寬 (例如 b 125000)");
  Serial.println("  c [CR]     : 設定編碼率分母 (例如 c 6 表示 4/6)");
  Serial.println("  l [Len]    : 設定封包長度 (預設 256 Bytes)");
  Serial.println("  u [UUID]   : 設定當前測試 UUID");
  Serial.println("  p          : 環境測試(SF7 慢速發送)");
  Serial.println("  6-12       : 正式測試開始(限制發射 100包)");
  Serial.println("  s [SF] [I] : 壓力測試(自定義 SF 與發射頻率)");
  Serial.println("  x          : 停止發射");
}