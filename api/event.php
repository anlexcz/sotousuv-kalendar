<?php
declare(strict_types=1);
require_once __DIR__ . '/../backend/bootstrap.php';
$id=(int)($_GET['id']??0);if(!$id)sk_json(['error'=>'missing_id'],400);
try{$e=sk_event_snapshot(sk_db(),(string)$id);if(!$e||$e['status']==='hidden')sk_json(['error'=>'not_found'],404);sk_json(['event'=>$e]);}catch(Throwable $e){sk_json(['error'=>'server_error'],500);}
