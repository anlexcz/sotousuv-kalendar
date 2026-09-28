<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once __DIR__.'/db.php';
$email=$argv[1]??'';$name=$argv[2]??'Administrátor';$password=$argv[3]??'';
if(!filter_var($email,FILTER_VALIDATE_EMAIL)||strlen($password)<10){fwrite(STDERR,"Usage: php backend/create_admin.php email@example.cz \"Jméno\" \"heslo-min-10\"\n");exit(1);}
$users=sk_table('users');$hash=password_hash($password,PASSWORD_DEFAULT);$q=sk_db()->prepare("INSERT INTO {$users}(email,password_hash,display_name,role,is_active) VALUES (?,?,?,\"admin\",1) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash),display_name=VALUES(display_name),role=\"admin\",is_active=1");$q->execute([$email,$hash,$name]);echo "Admin account ready: $email\n";
