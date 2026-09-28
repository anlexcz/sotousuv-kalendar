<?php
declare(strict_types=1);

const SK_ROOT = __DIR__ . '/..';

function sk_env(string $key, ?string $default = null): ?string
{
    $value = getenv($key);
    return ($value === false || $value === '') ? $default : $value;
}

function sk_config(): array
{
    static $config;
    if ($config !== null) return $config;

    $config = [
        'app_env' => sk_env('SK_APP_ENV', 'production'),
        'app_url' => rtrim((string) sk_env('SK_APP_URL', ''), '/'),
        'db' => [
            'host' => sk_env('SK_DB_HOST', '127.0.0.1'),
            'port' => (int) sk_env('SK_DB_PORT', '3306'),
            'name' => sk_env('SK_DB_NAME', 'sotousuv_kalendar'),
            'user' => sk_env('SK_DB_USER', 'sotousuv_kalendar'),
            'pass' => sk_env('SK_DB_PASS', ''),
            'charset' => 'utf8mb4',
        ],
        'session_name' => sk_env('SK_SESSION_NAME', 'sk_admin'),
        'session_secure' => sk_env('SK_SESSION_SECURE', '1') !== '0',
        'sheet_sync_token' => sk_env('SK_SHEET_SYNC_TOKEN', ''),
    ];
    return $config;
}
