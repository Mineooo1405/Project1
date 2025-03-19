#include <stdio.h>
#include <math.h>

#include "esp_log.h"

#include "omni_control.h"
#include "motor_handler.h"
#include "sys_config.h"
#include "pid_handler.h"
#include "LPF.h"

#define WHEEL_RADIUS 0.03   // Bán kính bánh xe (m)
#define ROBOT_RADIUS 0.1528 // Khoảng cách từ tâm robot đến bánh xe (m)
#define WEIGHT 2.0          // Trọng lượng robot (kg)
#define PI 3.14159265359

extern PID_t pid_motor[NUM_MOTORS];

extern LPF encoder_lpf[NUM_MOTORS];
// Quy đổi từ rad/s sang RPM
int m_s_to_rpm(float m_s)
{
    return (m_s * 1000) / PI; // 1 round = 3PI/50 m
}

float rad_s_to_rpm(float rad_s)
{
    return (rad_s * 60) / (2 * PI);
}

void calculate_wheel_speeds(const RobotParams *params, float *omega1, float *omega2, float *omega3)
{
    // Ma trận H^-1
    float H_inv[3][3] = {
        {-sin(params->theta), cos(params->theta), params->robot_radius},
        {-sin(M_PI / 3 - params->theta), -cos(M_PI / 3 - params->theta), params->robot_radius},
        {sin(M_PI / 3 + params->theta), -cos(M_PI / 3 + params->theta), params->robot_radius}};

    // Tính toán vận tốc góc
    *omega1 = (H_inv[0][0] * params->dot_x + H_inv[0][1] * params->dot_y + H_inv[0][2] * params->dot_theta) / params->wheel_radius;
    *omega2 = (H_inv[1][0] * params->dot_x + H_inv[1][1] * params->dot_y + H_inv[1][2] * params->dot_theta) / params->wheel_radius;
    *omega3 = (H_inv[2][0] * params->dot_x + H_inv[2][1] * params->dot_y + H_inv[2][2] * params->dot_theta) / params->wheel_radius;

    // printf("Omega1: %f, Omega2: %f, Omega3: %f\n", *omega1, *omega2, *omega3);
}
// Task chính để điều khiển robot
void omni_control(float dot_x, float dot_y, float dot_theta)
{
    float rpm[NUM_MOTORS];
    int pulse[NUM_MOTORS];
    int direction[NUM_MOTORS];

    float omega[NUM_MOTORS];
    RobotParams robot = {
        .dot_x = dot_x,
        .dot_y = dot_y,
        .dot_theta = dot_theta,
        .theta = 0,
        .wheel_radius = WHEEL_RADIUS,
        .robot_radius = ROBOT_RADIUS};

    // 🔹 Tính toán vận tốc góc cho từng bánh xe
    calculate_wheel_speeds(&robot, &omega[0], &omega[1], &omega[2]);

#if NON_PID == 1
    // 🔹 Chuyển đổi sang RPM và Pulse
    for (int i = 0; i < NUM_MOTORS; i++)
    {
        rpm[i] = rad_s_to_rpm(omega[i]);

        LPF_Clear(&encoder_lpf[i], rpm[i]);
        pulse[i] = rpm_to_pulse(rpm[i]);

        // Xác định hướng động cơ
        if (pulse[i] < 0)
        {
            direction[i] = 0; // Quay ngược
            pulse[i] = -pulse[i];
        }
        else
        {
            direction[i] = 1; // Quay xuôi
        }
    }

    // Sau khi tính toán xong, gửi lệnh đồng thời
    set_motor_speed(1, direction[0], pulse[0]);
    set_motor_speed(2, direction[1], pulse[1]);
    set_motor_speed(3, direction[2], pulse[2]);
#else
    for (int i = 0; i < NUM_MOTORS; i++)
    {
        rpm[i] = rad_s_to_rpm(omega[i]);
        LPF_Clear(&encoder_lpf[i], rpm[i]);
        pid_set_setpoint(&pid_motor[i], rpm[i]);
    }
#endif
}
