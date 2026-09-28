<?php
declare(strict_types=1);

require_once __DIR__ . '/../backend/bootstrap.php';

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

if ($method === 'GET') {
    sk_json(['user' => sk_current_user()]);
}

if ($method === 'POST') {
    $body = sk_body();
    $email = strtolower(trim((string) ($body['email'] ?? '')));
    $password = (string) ($body['password'] ?? '');

    $stmt = sk_db()->prepare('SELECT id, email, display_name, role, password_hash FROM users WHERE email = ? AND is_active = 1');
    $stmt->execute([$email]);
    $user = $stmt->fetch();

    if (!$user || !password_verify($password, $user['password_hash'])) {
        sk_json(['error' => 'invalid_credentials'], 401);
    }

    sk_start_session();
    session_regenerate_id(true);
    $_SESSION['user_id'] = (int) $user['id'];
    unset($user['password_hash']);
    sk_json(['user' => $user]);
}

if ($method === 'DELETE') {
    sk_start_session();
    $_SESSION = [];
    session_destroy();
    sk_json(['ok' => true]);
}

sk_json(['error' => 'method_not_allowed'], 405);
