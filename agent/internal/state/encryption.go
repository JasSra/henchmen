package state

import (
    "crypto/aes"
    "crypto/cipher"
    "crypto/rand"
    "crypto/sha256"
    "encoding/base64"
    "errors"
    "io"
)

// Cipher defines the interface used to encrypt/decrypt sensitive state values.
type Cipher interface {
    Encrypt([]byte) (string, error)
    Decrypt(string) ([]byte, error)
}

// NewAESCipher derives an AES-GCM cipher from the provided passphrase.
func NewAESCipher(passphrase string) (Cipher, error) {
    if passphrase == "" { return nil, errors.New("passphrase required for encryption") }
    key := sha256.Sum256([]byte(passphrase))
    block, err := aes.NewCipher(key[:])
    if err != nil { return nil, err }
    gcm, err := cipher.NewGCM(block)
    if err != nil { return nil, err }
    return &aesCipher{gcm: gcm}, nil
}

type aesCipher struct { gcm cipher.AEAD }

func (a *aesCipher) Encrypt(data []byte) (string, error) {
    nonce := make([]byte, a.gcm.NonceSize())
    if _, err := io.ReadFull(rand.Reader, nonce); err != nil { return "", err }
    sealed := a.gcm.Seal(nonce, nonce, data, nil)
    return base64.StdEncoding.EncodeToString(sealed), nil
}

func (a *aesCipher) Decrypt(encoded string) ([]byte, error) {
    raw, err := base64.StdEncoding.DecodeString(encoded)
    if err != nil { return nil, err }
    if len(raw) < a.gcm.NonceSize() { return nil, errors.New("ciphertext too short") }
    nonce := raw[:a.gcm.NonceSize()]
    cipherText := raw[a.gcm.NonceSize():]
    return a.gcm.Open(nil, nonce, cipherText, nil)
}
