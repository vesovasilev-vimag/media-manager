import js from '@eslint/js'
import ts from 'typescript-eslint'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import prettier from 'eslint-config-prettier'
export default [js.configs.recommended, ...ts.configs.recommended, ...vue.configs['flat/recommended'], { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: ts.parser } } }, { languageOptions: { globals: { ...globals.browser, ...globals.node } }, rules: { 'vue/multi-word-component-names': 'off' } }, prettier]
