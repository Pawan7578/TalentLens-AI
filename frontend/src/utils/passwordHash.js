/**
 * Pre-hash long passwords on client-side to stay within bcrypt's 72-byte limit
 * Shorter passwords are returned as-is for backward compatibility
 *
 * @param {string} password - The plain password to prepare
 * @returns {Promise<string>} - Original password if <= 72 bytes, SHA-256 hash otherwise
 */
export const preparePassword = async (password) => {
  const encoder = new TextEncoder();
  const byteLength = encoder.encode(password).length;

  // If password is within bcrypt limit, return as-is
  if (byteLength <= 72) {
    return password;
  }

  // Hash long passwords to fixed length using SHA-256
  const data = encoder.encode(password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

  // Return first 72 characters (fits within bcrypt's byte limit)
  return hashHex.slice(0, 72);
};

/**
 * Calculate byte length of a password (UTF-8 encoded)
 * @param {string} password - The password to measure
 * @returns {number} - Byte length
 */
export const getPasswordByteLength = (password) => {
  const encoder = new TextEncoder();
  return encoder.encode(password).length;
};
