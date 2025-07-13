const webpack = require("webpack");
const { resolve } = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const nodeExternals = require("webpack-node-externals");
const CopyPlugin = require("copy-webpack-plugin");
const { ServiceWorkerPlugin } = require("service-worker-webpack");
const fs = require("fs");
const path = require("path");
const {
  bundledSyntaxHighlighters,
  lazySyntaxHighlighters,
} = require("./src/shared/build-config");

// .env 파일 로드
const envPath = path.resolve(__dirname, '.env');
let envVars = {};

// .env 파일이 존재하면 읽기
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf8');
  
  // 간단한 .env 파서 (dotenv 패키지 없이)
  envContent.split('\n').forEach(line => {
    // 주석이나 빈 줄 무시
    if (!line || line.startsWith('#')) return;
    
    const parts = line.split('=');
    if (parts.length === 2) {
      const key = parts[0].trim();
      const value = parts[1].trim();
      
      // 따옴표 제거 (있을 경우)
      envVars[`process.env.${key}`] = JSON.stringify(
        value.replace(/^["'](.*)["']$/, '$1')
      );
    }
  });
}

// Docker 컨테이너 환경에서 전달된 환경변수도 확인
// Docker 환경변수가 우선순위를 가짐
const dockerEnvVars = [
  'LEMMY_API_KEY',
  'LEMMY_BCH_API_URL', 
  'LEMMY_BCH_PAYMENT_URL',
  'COMMIT_HASH'
];

dockerEnvVars.forEach(key => {
  if (process.env[key]) {
    envVars[`process.env.${key}`] = JSON.stringify(process.env[key]);
  }
});

// process.env.COMMIT_HASH가 없으면 'latest'로 기본값 설정
if (!envVars["process.env.COMMIT_HASH"]) {
  envVars["process.env.COMMIT_HASH"] = JSON.stringify("latest");
}

// BCH 관련 환경변수 기본값 설정 (실제 도메인으로 업데이트)
if (!envVars["process.env.LEMMY_BCH_PAYMENT_URL"]) {
  envVars["process.env.LEMMY_BCH_PAYMENT_URL"] = JSON.stringify("https://payments.defadb.com/");
}
if (!envVars["process.env.LEMMY_BCH_API_URL"]) {
  envVars["process.env.LEMMY_BCH_API_URL"] = JSON.stringify("https://payments.defadb.com/api/user_credit");
}
// API 키는 환경변수에서만 가져오도록 수정 (하드코딩 제거)
if (!envVars["process.env.LEMMY_API_KEY"]) {
  envVars["process.env.LEMMY_API_KEY"] = JSON.stringify(process.env.LEMMY_API_KEY || "");
}

const banner = `
  hash:[contentHash], chunkhash:[chunkhash], name:[name], filebase:[base], query:[query], file:[file]
  Source code: https://github.com/LemmyNet/lemmy-ui
  Created by dessalines
  @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL v3.0
  `;

const contextPlugin = (() => {
  const check = x => x.match(/^[0-9a-zA-Z-]+$/);
  const eagerNames = bundledSyntaxHighlighters.filter(check).join("|");
  const eagerHljs = new RegExp(`^[.][/\\\\](${eagerNames})[.]js\$`);
  let lazyHljs;
  if (lazySyntaxHighlighters === "*") {
    lazyHljs = new RegExp(`^[.][/\\\\](?!(${eagerNames})[.]js\$)[^.]+[.]js\$`);
  } else {
    const lazyNames = lazySyntaxHighlighters.filter(check).join("|");
    lazyHljs = new RegExp(`^[.][/\\\\](${lazyNames})[.]js\$`);
  }

  // Plugin will be used for all parameterized dynamic imports.
  return new webpack.ContextReplacementPlugin(/.*/, options => {
    if (/^highlight.js\/lib\/languages$/.test(options.request)) {
      if (options.mode == "eager") {
        options.regExp = eagerHljs;
      } else {
        options.regExp = lazyHljs;
      }
    } else if (/^date-fns\/locale$/.test(options.request)) {
    } else {
      return;
    }
    options.recursive = false;
    options.request = resolve(__dirname, "node_modules/" + options.request);
  });
})();

module.exports = (env, argv) => {
  const mode = argv.mode;

  const base = {
    output: {
      hashFunction: "xxhash64",
    },
    resolve: {
      extensions: [".js", ".jsx", ".ts", ".tsx"],
      alias: {
        "@": resolve(__dirname, "src/"),
        "@utils": resolve(__dirname, "src/shared/utils/"),
      },
    },
    performance: {
      hints: false,
    },
    module: {
      rules: [
        {
          test: /\.(scss|css)$/i,
          use: [MiniCssExtractPlugin.loader, "css-loader", "sass-loader"],
        },
        {
          test: /\.(js|jsx|tsx|ts)$/, // All ts and tsx files will be process by
          exclude: /node_modules/, // ignore node_modules
          loader: "babel-loader",
        },
        // Due to some weird babel issue: https://github.com/webpack/webpack/issues/11467
        {
          test: /\.m?js/,
          resolve: {
            fullySpecified: false,
          },
        },
      ],
    },
    plugins: [
      new webpack.DefinePlugin({
        ...envVars,
        "process.env.COMMIT_HASH": envVars["process.env.COMMIT_HASH"] || JSON.stringify("latest"),
        "process.env.NODE_ENV": `"${mode}"`
      }),
      new MiniCssExtractPlugin({
        filename: "styles/styles.css",
      }),
      new CopyPlugin({
        patterns: [{ from: "./src/assets", to: "./assets" }],
      }),
      new webpack.BannerPlugin({
        banner,
      }),
      contextPlugin,
    ],
  };

  const serverConfig = {
    ...base,
    entry: "./src/server/index.tsx",
    output: {
      ...base.output,
      filename: "js/server.js",
      publicPath: "/",
      chunkLoading: false, // everything bundled
    },
    target: "node",
    externals: [nodeExternals(), "inferno-helmet"],
  };

  const clientConfig = {
    ...base,
    entry: "./src/client/index.tsx",
    output: {
      ...base.output,
      filename: "js/client.js",
      publicPath: `/static/${JSON.parse(envVars["process.env.COMMIT_HASH"] || '"latest"')}/`,
      chunkFilename: "js/[name].client.js", // predictable names for manual preload
    },
    plugins: [
      ...base.plugins,
      // 클라이언트에서 process 객체 사용할 수 있게 폴리필 추가
      new webpack.ProvidePlugin({
        process: 'process/browser',
      }),
      new ServiceWorkerPlugin({
        enableInDevelopment: mode !== "development", // this may seem counterintuitive, but it is correct
        workbox: {
          cacheId: "lemmy",
          include: [/(assets|styles|js)\/.+\..+$/g],
          inlineWorkboxRuntime: true,
          runtimeCaching: [
            {
              urlPattern: ({
                sameOrigin,
                url: { pathname, host },
                request: { method },
              }) =>
                (sameOrigin || host.includes("defadb.com")) &&
                (!(
                  pathname.includes("pictrs") || pathname.includes("static")
                ) ||
                  method === "POST"),
              handler: "NetworkFirst",
              options: {
                cacheName: "instance-cache",
              },
            },
            {
              urlPattern: ({ url: { pathname, host }, sameOrigin }) =>
                (sameOrigin || host.includes("defadb.com")) &&
                pathname.includes("static"),
              handler: mode === "development" ? "NetworkFirst" : "CacheFirst",
              options: {
                cacheName: "static-cache",
                expiration: {
                  maxAgeSeconds: 60 * 60 * 24,
                },
              },
            },
            {
              urlPattern: ({ url: { pathname }, request: { method } }) =>
                pathname.includes("pictrs") && method === "GET",
              handler: "StaleWhileRevalidate",
              options: {
                cacheName: "image-cache",
                expiration: {
                  maxAgeSeconds: 60 * 60 * 24,
                },
              },
            },
          ],
        },
      }),
    ],
  };

  if (mode === "development") {
    // serverConfig.cache = {
    //   type: "filesystem",
    //   name: "server",
    // };

    const RunNodeWebpackPlugin = require("run-node-webpack-plugin");
    serverConfig.plugins.push(
      new RunNodeWebpackPlugin({ runOnlyInWatchMode: true }),
    );
  } else if (mode === "none") {
    const { BundleAnalyzerPlugin } = require("webpack-bundle-analyzer");
    serverConfig.plugins.push(new BundleAnalyzerPlugin());
  }

  return [serverConfig, clientConfig];
};
