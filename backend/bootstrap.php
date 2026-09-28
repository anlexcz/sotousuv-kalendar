<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';

function sk_json(mixed $data, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function sk_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') return [];
    $data = json_decode($raw, true);
    if (!is_array($data)) sk_json(['error' => 'invalid_json'], 400);
    return $data;
}

function sk_start_session(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) return;
    $config = sk_config();
    session_name($config['session_name']);
    session_set_cookie_params(['httponly'=>true,'secure'=>$config['session_secure'],'samesite'=>'Lax','path'=>'/']);
    session_start();
}

function sk_current_user(): ?array
{
    sk_start_session();
    $id = $_SESSION['user_id'] ?? null;
    if (!$id) return null;
    $users = sk_table('users');
    $stmt = sk_db()->prepare("SELECT id, email, display_name, role FROM {$users} WHERE id = ? AND is_active = 1");
    $stmt->execute([$id]);
    return $stmt->fetch() ?: null;
}

function sk_require_user(): array
{
    $user = sk_current_user();
    if (!$user) sk_json(['error'=>'unauthorized'],401);
    return $user;
}

function sk_event_snapshot(PDO $db, string $eventId): array
{
    $events = sk_table('events');
    $dates = sk_table('event_dates');
    $categories = sk_table('event_categories');
    $locations = sk_table('event_locations');
    $sources = sk_table('event_sources');

    $stmt = $db->prepare("SELECT * FROM {$events} WHERE id = ?");
    $stmt->execute([$eventId]);
    $event = $stmt->fetch();
    if (!$event) return [];

    foreach ([
        'dates' => "SELECT starts_on, ends_on, starts_at, ends_at, sort_order FROM {$dates} WHERE event_id = ? ORDER BY sort_order, starts_on",
        'categories' => "SELECT category FROM {$categories} WHERE event_id = ? ORDER BY category",
        'locations' => "SELECT label, sort_order FROM {$locations} WHERE event_id = ? ORDER BY sort_order, id",
        'sources' => "SELECT id, url, label, is_primary, source_key, last_seen_at FROM {$sources} WHERE event_id = ? ORDER BY is_primary DESC, id",
    ] as $key => $sql) {
        $q = $db->prepare($sql);$q->execute([$eventId]);$rows=$q->fetchAll();
        $event[$key] = $key === 'categories' ? array_column($rows,'category') : $rows;
    }
    return $event;
}
