<?php
declare(strict_types=1);

require_once __DIR__ . '/../../backend/bootstrap.php';
sk_require_user();

try {
    $db = sk_db();
    $q = trim((string) ($_GET['q'] ?? ''));
    $where = [];
    $params = [];

    if ($q !== '') {
        $where[] = '(e.title LIKE ? OR e.city LIKE ? OR e.place LIKE ? OR e.region LIKE ?)';
        $like = '%' . $q . '%';
        array_push($params, $like, $like, $like, $like);
    }

    $sql = 'SELECT e.id FROM events e' . ($where ? ' WHERE ' . implode(' AND ', $where) : '') .
        ' ORDER BY (SELECT MIN(d.starts_on) FROM event_dates d WHERE d.event_id=e.id) DESC, e.updated_at DESC LIMIT 1000';
    $stmt = $db->prepare($sql);
    $stmt->execute($params);

    $events = [];
    foreach ($stmt->fetchAll() as $row) {
        $events[] = sk_event_snapshot($db, $row['id']);
    }

    $pending = (int) $db->query("SELECT COUNT(*) FROM event_change_proposals WHERE status='pending'")->fetchColumn();
    sk_json(['events' => $events, 'pending_proposals' => $pending]);
} catch (Throwable $e) {
    sk_json(['error' => 'server_error'], 500);
}
