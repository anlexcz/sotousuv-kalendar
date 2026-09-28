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
            // Shared Metrobus database: do not assume a dedicated DB exists.
            'name' => sk_env('SK_DB_NAME', ''),
            'user' => sk_env('SK_DB_USER', ''),
            'pass' => sk_env('SK_DB_PASS', ''),
            'charset' => 'utf8mb4',
            'table_prefix' => sk_env('SK_DB_TABLE_PREFIX', 'sk_'),
        ],
        'session_name' => sk_env('SK_SESSION_NAME', 'sk_admin'),
        'session_secure' => sk_env('SK_SESSION_SECURE', '1') !== '0',
        'sheet_sync_token' => sk_env('SK_SHEET_SYNC_TOKEN', ''),
    ];
    return $config;
}

function sk_table(string $name): string
{
    $prefix = (string) sk_config()['db']['table_prefix'];
    if (!preg_match('/^[A-Za-z0-9_]+$/', $prefix) || !preg_match('/^[A-Za-z0-9_]+$/', $name)) {
        throw new RuntimeException('Invalid database table name.');
    }
    return $prefix . $name;
}
