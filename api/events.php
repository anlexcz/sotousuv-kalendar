<?php
declare(strict_types=1);
require_once __DIR__ . '/../backend/bootstrap.php';
try {
    $db=sk_db();$eventsT=sk_table('events');$datesT=sk_table('event_dates');
    $from=$_GET['from']??date('Y-m-d');$to=$_GET['to']??null;$search=trim((string)($_GET['q']??''));$status=$_GET['status']??'active';
    $where=['e.status = ?'];$params=[$status];
    $where[]="EXISTS (SELECT 1 FROM {$datesT} d WHERE d.event_id=e.id AND d.ends_on>=?)";$params[]=$from;
    if($to){$where[]="EXISTS (SELECT 1 FROM {$datesT} d2 WHERE d2.event_id=e.id AND d2.starts_on<=?)";$params[]=$to;}
    if($search!==''){$where[]='(e.title LIKE ? OR e.city LIKE ? OR e.place LIKE ? OR e.region LIKE ?)';$like='%'.$search.'%';array_push($params,$like,$like,$like,$like);}
    $sql="SELECT e.* FROM {$eventsT} e WHERE ".implode(' AND ',$where)." ORDER BY (SELECT MIN(d.starts_on) FROM {$datesT} d WHERE d.event_id=e.id AND d.ends_on>=?) ASC,e.title ASC LIMIT 500";
    $params[]=$from;$stmt=$db->prepare($sql);$stmt->execute($params);$events=[];foreach($stmt->fetchAll() as $row)$events[]=sk_event_snapshot($db,(string)$row['id']);
    sk_json(['events'=>$events]);
}catch(Throwable $e){sk_json(['error'=>'server_error'],500);}
