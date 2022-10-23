# Set hostname and port of the MQTT broker
broker = 'hostname.domainname'
port = 8883

# Set username and password for MQTT connection.
# If user authentication not required, remove these.
username = 'mqttuser'
password = 'mqttpassowrd'

# Set TLS CA certificate file to authenticate the MQTT broker.
# If you do not need server authentication, remove this.
ca_cert = "certs/ca.crt"

# Set TLS client certificate and client key file for MQTT connection.
# If client certificate is not required, remove these.
certfile = "certs/client.crt"
keyfile = "certs/client.key"
