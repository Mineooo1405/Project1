#include <WiFi.h>
#include <ArduinoWebsockets.h> //0.52

using namespace websockets;

const char* ssid = "he";  
const char* password = "hi";  
const char* ws_server = "ws://<address>:8000/ws/robot/1";  // Thay bằng IP máy chạy FastAPI

WebsocketsClient client;

// Hàm xử lý khi nhận tin nhắn từ server
void onMessageCallback(WebsocketsMessage message) {
    Serial.print(" Received from server: ");
    Serial.println(message.data());
}

void setup() {
    Serial.begin(115200);
    WiFi.begin(ssid, password);
    
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        Serial.print(".");
    }
    Serial.println("\n Connected to WiFi!");
    
    client.onMessage(onMessageCallback);
    Serial.println("Connecting to WebSocket server...");

    if (client.connect(ws_server)) {
        Serial.println(" Connected to WebSocket!");
        client.send("ESP32 connected");
    } else {
        Serial.println(" WebSocket connection failed!");
    }
}

void loop() {
    if (client.available()) {
        client.send("ESP32 heartbeat");  // Gửi tín hiệu mỗi 5 giây
    }
    client.poll();
    delay(5000);
}
