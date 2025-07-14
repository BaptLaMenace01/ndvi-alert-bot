import os
import requests
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_telegram_message(message, image_path=None):
    """
    Envoie un message (et optionnellement une image) via le bot Lithium dédié.
    Lit les variables d'env. LITHIUM_TELEGRAM_TOKEN et LITHIUM_TELEGRAM_CHAT_ID.
    """
    token = os.getenv("LITHIUM_TELEGRAM_TOKEN")
    chat_id = os.getenv("LITHIUM_TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.error("❌ LITHIUM_TELEGRAM_TOKEN ou LITHIUM_TELEGRAM_CHAT_ID manquant")
        return False
    
    logger.info(f"📤 Envoi message Telegram à {chat_id}")
    
    # Envoi du message texte
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        logger.info(f"📤 Status message: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                logger.info("✅ Message texte envoyé avec succès")
            else:
                logger.error(f"❌ Erreur API Telegram: {result}")
                # Retenter avec chat_id en integer
                if str(chat_id).isdigit():
                    logger.info("🔄 Nouvelle tentative avec chat_id en integer")
                    payload["chat_id"] = int(chat_id)
                    response = requests.post(url, json=payload, timeout=10)
                    if response.status_code == 200 and response.json().get("ok"):
                        logger.info("✅ Message envoyé avec chat_id integer")
                    else:
                        logger.error(f"❌ Échec avec chat_id integer: {response.text}")
                        return False
                else:
                    return False
        else:
            logger.error(f"❌ Erreur HTTP message: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de l'envoi du message")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur réseau message: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur inattendue message: {e}")
        return False
    
    # Envoi de l'image si fournie
    if image_path and os.path.exists(image_path):
        logger.info(f"📤 Envoi image: {image_path}")
        photo_url = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        try:
            with open(image_path, 'rb') as f:
                files = {'photo': f}
                data = {'chat_id': str(chat_id)}
                response = requests.post(photo_url, data=data, files=files, timeout=15)
                
            logger.info(f"📤 Status image: {response.status_code}")
            if response.status_code == 200 and response.json().get("ok"):
                logger.info("✅ Image envoyée avec succès")
                return True
            else:
                logger.error(f"❌ Erreur envoi image: {response.text}")
                return False
                    
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout lors de l'envoi de l'image")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau image: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur inattendue image: {e}")
            return False
    
    return True
