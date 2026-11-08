package cn.aidaily.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** AI 晨报安卓版：独立窗口，在线看最新一期，断网自动切到内置的往期。 */
public class MainActivity extends Activity {

    // 入口地址不写死：源码里是占位符，打包时由 tools/build_apk.py 从
    // site/config.js 的 siteUrl 注入到 .build/gen 下的副本，再编译那份。
    // 这样仓库里永远没有明文，打出来的包又指向真实入口。
    private static final String ONLINE  = "__SITE_URL__";
    private static final String OFFLINE = "file:///android_asset/site/index.html";
    private static final String HOST    = "__SITE_HOST__";

    // 更新清单由 build_apk.py 打包后写到站点根目录，字段里带 versionCode。
    // 地址不另存一份：由入口地址派生，sharecode 也跟着带过去（线上无码即 403）。
    private static final String MANIFEST = "version.json";
    // 同一个版本 24 小时内只问一次：不更新的人不该每次开 App 都被拦一下。
    private static final long ASK_GAP_MS = 24L * 60 * 60 * 1000;

    private WebView web;
    private boolean offline = false;
    private boolean settled = false;
    private boolean checked = false;
    private int selfCode = 0;
    private String selfName = "";
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= 21) {
            getWindow().setStatusBarColor(Color.rgb(0x8c, 0x1d, 0x18));
        }

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setAllowFileAccessFromFileURLs(true);
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportZoom(true);
        s.setBuiltInZoomControls(true);
        s.setDisplayZoomControls(false);

        web.addJavascriptInterface(new Bridge(), "AIDaily");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, String url) {
                return route(url);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                return route(req.getUrl().toString());
            }
            @Override public void onPageFinished(WebView v, String url) {
                settled = true;
            }
            @Override public void onReceivedError(WebView v, int code, String desc, String failingUrl) {
                if (failingUrl != null && failingUrl.startsWith(HOST)) fallback();
            }
            @Override public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (Build.VERSION.SDK_INT >= 23 && req.isForMainFrame()
                        && req.getUrl().toString().startsWith(HOST)) fallback();
            }
        });

        readSelfVersion();
        loadOnline();

        // 首屏先出来，再悄悄问一次版本；失败一律静默，不挡看报。
        handler.postDelayed(new Runnable() {
            @Override public void run() { checkUpdate(); }
        }, 2000);
    }

    private boolean route(String url) {
        if (url.startsWith(HOST) || url.startsWith("file:///android_asset/")) return false;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) { }
        return true;
    }

    private void loadOnline() {
        offline = false;
        settled = false;
        web.loadUrl(ONLINE);
        // 网络不通或迟迟打不开时，别让用户对着白屏
        handler.postDelayed(new Runnable() {
            @Override public void run() {
                if (!settled && !offline) fallback();
            }
        }, 9000);
    }

    private void fallback() {
        if (offline) return;
        offline = true;
        handler.post(new Runnable() {
            @Override public void run() { web.loadUrl(OFFLINE); }
        });
    }

    // ---------- 更新检查 ----------
    // 版本号的唯一事实源是这个包自己（PackageManager），不靠打包时再注入一份常量：
    // 注入值一旦和实际 versionCode 差一，就会出现「明明装了新版却一直提示更新」。
    @SuppressWarnings("deprecation")
    private void readSelfVersion() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            selfCode = pi.versionCode;
            selfName = pi.versionName == null ? "" : pi.versionName;
        } catch (Exception e) {
            selfCode = 0;              // 读不到就别检查，宁可不提示也不能误报
            selfName = "";
        }
    }

    /** 入口里的查询串（sharecode 是访问门槛，清单和安装包都得带着它）。 */
    private static String queryOf(String url) {
        int q = url.indexOf('?');
        return q < 0 ? "" : url.substring(q);
    }

    private static String manifestUrl() {
        return HOST + MANIFEST + queryOf(ONLINE);
    }

    private static String downloadUrl() {
        return HOST + "ai-daily.apk" + queryOf(ONLINE);
    }

    private void checkUpdate() {
        if (checked || offline || selfCode <= 0) return;
        checked = true;
        final String url = manifestUrl();
        new Thread(new Runnable() {
            @Override public void run() {
                String body = httpGet(url);
                if (body == null) return;
                int rc;
                String rn;
                try {
                    JSONObject o = new JSONObject(body);
                    rc = o.optInt("code", 0);
                    rn = o.optString("name", "");
                } catch (Exception e) {
                    return;            // 403 页面 / 代理插页：不是清单就当没有更新
                }
                if (rc <= selfCode) return;
                final int code = rc;
                final String name = rn;
                handler.post(new Runnable() {
                    @Override public void run() { maybePrompt(code, name); }
                });
            }
        }, "update-check").start();
    }

    /** 只读清单：超时、断网、非 200 全部当作「没有更新」，绝不弹错误提示。 */
    private static String httpGet(String url) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(8000);
            c.setReadTimeout(8000);
            c.setRequestProperty("User-Agent", "AIDaily-Android");
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("Cache-Control", "no-cache");
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                if (out.size() > 16384) {   // 清单只有几百字节，超了必是异常页面
                    in.close();
                    return null;
                }
            }
            in.close();
            return new String(out.toByteArray(), "UTF-8");
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void maybePrompt(int remoteCode, String remoteName) {
        if (remoteCode <= selfCode || isFinishing() || isDestroyed()) return;

        SharedPreferences sp = getSharedPreferences("update", MODE_PRIVATE);
        if (sp.getInt("asked_code", 0) == remoteCode
                && System.currentTimeMillis() - sp.getLong("asked_at", 0) < ASK_GAP_MS) {
            return;
        }
        sp.edit().putInt("asked_code", remoteCode)
                 .putLong("asked_at", System.currentTimeMillis()).apply();

        String mine = selfName.isEmpty() ? String.valueOf(selfCode) : selfName;
        String theirs = remoteName.isEmpty() ? String.valueOf(remoteCode) : remoteName;
        new AlertDialog.Builder(this)
                .setTitle("有新版本 " + theirs)
                .setMessage("当前版本 " + mine + "。\n更新后可离线查看最近 8 期，"
                            + "装完直接覆盖，不用先卸载。")
                .setPositiveButton("去更新", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { openDownload(); }
                })
                .setNegativeButton("以后再说", null)
                .show();
    }

    private void openDownload() {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(downloadUrl())));
        } catch (Exception ignored) { }
    }

    public class Bridge {
        @JavascriptInterface public boolean isApk() { return true; }
        @JavascriptInterface public void reload() {
            handler.post(new Runnable() {
                @Override public void run() { loadOnline(); }
            });
        }
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
