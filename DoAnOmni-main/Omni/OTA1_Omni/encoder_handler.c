#include "encoder_handler.h"
#include "gpio_handler.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "esp_log.h"
#include "lwip/sockets.h"

static const char *TAG = "Encoder";

volatile int encoder1_count = 0;
volatile int encoder2_count = 0;
volatile int encoder3_count = 0;

volatile int encoder1_a_prev = 0, encoder1_b_prev = 0;
volatile int encoder2_a_prev = 0, encoder2_b_prev = 0;
volatile int encoder3_a_prev = 0, encoder3_b_prev = 0;

volatile int encoder1_rpm = 0;
volatile int encoder2_rpm = 0;
volatile int encoder3_rpm = 0;

static void IRAM_ATTR encoder1_isr_handler(void *arg)
{
    int A = gpio_get_level(ENCODER_1_A);
    int B = gpio_get_level(ENCODER_1_B);

    // Dựa trên trạng thái trước đó và hiện tại để xác định hướng
    if ((encoder1_a_prev == 0 && encoder1_b_prev == 0 && A == 0 && B == 1) ||
        (encoder1_a_prev == 0 && encoder1_b_prev == 1 && A == 1 && B == 1) ||
        (encoder1_a_prev == 1 && encoder1_b_prev == 1 && A == 1 && B == 0) ||
        (encoder1_a_prev == 1 && encoder1_b_prev == 0 && A == 0 && B == 0))
    {
        encoder1_count++;
    }
    else
    {
        encoder1_count--;
    }

    encoder1_a_prev = A;
    encoder1_b_prev = B;
}

static void IRAM_ATTR encoder2_isr_handler(void *arg)
{
    int A = gpio_get_level(ENCODER_2_A);
    int B = gpio_get_level(ENCODER_2_B);

    if ((encoder2_a_prev == 0 && encoder2_b_prev == 0 && A == 0 && B == 1) ||
        (encoder2_a_prev == 0 && encoder2_b_prev == 1 && A == 1 && B == 1) ||
        (encoder2_a_prev == 1 && encoder2_b_prev == 1 && A == 1 && B == 0) ||
        (encoder2_a_prev == 1 && encoder2_b_prev == 0 && A == 0 && B == 0))
    {
        encoder2_count++;
    }
    else
    {
        encoder2_count--;
    }

    encoder2_a_prev = A;
    encoder2_b_prev = B;
}

static void IRAM_ATTR encoder3_isr_handler(void *arg)
{
    int A = gpio_get_level(ENCODER_3_A);
    int B = gpio_get_level(ENCODER_3_B);

    if ((encoder3_a_prev == 0 && encoder3_b_prev == 0 && A == 0 && B == 1) ||
        (encoder3_a_prev == 0 && encoder3_b_prev == 1 && A == 1 && B == 1) ||
        (encoder3_a_prev == 1 && encoder3_b_prev == 1 && A == 1 && B == 0) ||
        (encoder3_a_prev == 1 && encoder3_b_prev == 0 && A == 0 && B == 0))
    {
        encoder3_count++;
    }
    else
    {
        encoder3_count--;
    }

    encoder3_a_prev = A;
    encoder3_b_prev = B;
}

void setup_encoders()
{
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_ANYEDGE, // Bắt cả sườn lên và xuống
        .mode = GPIO_MODE_INPUT,
        .pin_bit_mask = (1ULL << ENCODER_1_A) | (1ULL << ENCODER_1_B) |
                        (1ULL << ENCODER_2_A) | (1ULL << ENCODER_2_B) |
                        (1ULL << ENCODER_3_A) | (1ULL << ENCODER_3_B),
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE};
    gpio_config(&io_conf);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(ENCODER_1_A, encoder1_isr_handler, NULL);
    gpio_isr_handler_add(ENCODER_1_B, encoder1_isr_handler, NULL);
    gpio_isr_handler_add(ENCODER_2_A, encoder2_isr_handler, NULL);
    gpio_isr_handler_add(ENCODER_2_B, encoder2_isr_handler, NULL);
    gpio_isr_handler_add(ENCODER_3_A, encoder3_isr_handler, NULL);
    gpio_isr_handler_add(ENCODER_3_B, encoder3_isr_handler, NULL);
    ESP_LOGW(TAG, "Setup Encoder Done");
}
void clear_encoders()
{
    encoder1_count = 0;
    encoder2_count = 0;
    encoder3_count = 0;
}

void calculate_RPM()
{
    // Tính toán vận tốc góc của encoder
    encoder1_rpm = encoder1_count * 60 / PULSE_PER_ROUND;
    encoder2_rpm = encoder2_count * 60 / PULSE_PER_ROUND;
    encoder3_rpm = encoder3_count * 60 / PULSE_PER_ROUND;
    clear_encoders();
}

void task_send_encoder(void *pvParameters)
{
    int sock = *(int *)pvParameters;
    ESP_LOGI(TAG, "Start Encoder Task");

    char message[64];
    // char encoder_message[64];

    while (1)
    {
        // snprintf(encoder_message, sizeof(encoder_message), "1:%d;2:%d;3:%d", encoder1_count, encoder2_count, encoder3_count);
        calculate_RPM();
        snprintf(message, sizeof(message), "1:%d;2:%d;3:%d", encoder1_rpm, encoder2_rpm, encoder3_rpm);
        if (send(sock, message, strlen(message), 0) < 0)
        {
            ESP_LOGE(TAG, "Failed to send encoder data");
        }
        else
        {
            printf("Sent: %s\n", message);
            // ESP_LOGW(TAG, "%s", message);
        }
        vTaskDelay(1000 / portTICK_PERIOD_MS);
    }
}