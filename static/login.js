(function () {
  // --- Page status: prove JS ran without any POST ---
  var badge = document.getElementById("js-status");
  if (badge) {
    badge.textContent = "JavaScript loaded ✔";
    badge.classList.remove("error");
    badge.classList.add("success"); // style .success in your CSS if you want
  }

  // Optional: hidden flag to confirm JS ran on submit payloads
  var jsReady = document.getElementById("js_ready");
  if (jsReady) jsReady.value = "1";

  console.log("[login.js] loaded");

  // --- Minimal SHA-256 (hex) ---
  function utf8(s){ return unescape(encodeURIComponent(s)); }
  function toWords(s){
    var l = s.length, w = [], i = 0, t = 0;
    for (; i < l; i++) { t = (t<<8) | s.charCodeAt(i); if ((i & 3) === 3) { w.push(t); t = 0; } }
    if ((l & 3) !== 0) { w.push(t << (8 * (3 - (l & 3)))); }
    return { w:w, len:l };
  }
  function pad(w, len){
    var bl = len * 8;
    w.push(0x80 << 24);
    while ((w.length % 16) !== 14) w.push(0);
    w.push((bl / Math.pow(2,32)) | 0);
    w.push(bl & 0xffffffff);
  }
  function hex(n){ return ("00000000" + (n >>> 0).toString(16)).slice(-8); }
  function sha256(str){
    var K=[1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298];
    var H=[1779033703,3144134277,1013904242,2773480762,1359893119,2600822924,528734635,1541459225];
    var s=utf8(str), o=toWords(s), w=o.w.slice(0); pad(w,o.len);
    for (var i=0;i<w.length;i+=16){
      var W=w.slice(i,i+16), a=H[0], b=H[1], c=H[2], d=H[3], e=H[4], f=H[5], g=H[6], h=H[7];
      for (var j=16;j<64;j++){
        var s0=(W[j-15]>>>7|W[j-15]<<25)^(W[j-15]>>>18|W[j-15]<<14)^(W[j-15]>>>3);
        var s1=(W[j-2]>>>17|W[j-2]<<15)^(W[j-2]>>>19|W[j-2]<<13)^(W[j-2]>>>10);
        W[j]=(W[j-16]+s0+W[j-7]+s1)|0;
      }
      for (var k=0;k<64;k++){
        var S1=(e>>>6|e<<26)^(e>>>11|e<<21)^(e>>>25|e<<7), ch=(e&f)^((~e)&g);
        var t1=(h+S1+ch+K[k]+W[k])|0, S0=(a>>>2|a<<30)^(a>>>13|a<<19)^(a>>>22|a<<10), maj=(a&b)^(a&c)^(b&c), t2=(S0+maj)|0;
        h=g; g=f; f=e; e=(d+t1)|0; d=c; c=b; b=a; a=(t1+t2)|0;
      }
      H[0]=(H[0]+a)|0; H[1]=(H[1]+b)|0; H[2]=(H[2]+c)|0; H[3]=(H[3]+d)|0;
      H[4]=(H[4]+e)|0; H[5]=(H[5]+f)|0; H[6]=(H[6]+g)|0; H[7]=(H[7]+h)|0;
    }
    return hex(H[0])+hex(H[1])+hex(H[2])+hex(H[3])+hex(H[4])+hex(H[5])+hex(H[6])+hex(H[7]);
  }

  // --- Wire the login form: hash visible pwd into hidden named field ---
  function wireForm(formId, visiblePwdId, hiddenPwdId) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener("submit", function () {
      console.log("[login.js] submit fired");
      try {
        var vis = document.getElementById(visiblePwdId);
        var hid = document.getElementById(hiddenPwdId);
        if (vis && hid && vis.value) {
          hid.value = sha256(vis.value);
          // Optional: wipe plaintext after hashing (if you prefer):
          // vis.value = "";
        }
      } catch (e) {
        console.warn("[login.js] hashing failed; submitting anyway.", e);
      }
      // No preventDefault — always submit
    });
  }

  wireForm("login-form", "password_visible", "password_hashed");

  wireForm("register-form", "reg_password_visible", "reg_password_hashed");
})();
