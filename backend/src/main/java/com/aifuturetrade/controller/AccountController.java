package com.aifuturetrade.controller;

import com.aifuturetrade.service.AccountService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 控制器：账户管理
 */
@RestController
@RequestMapping("/api/accounts")
@Tag(name = "账户管理", description = "账户管理接口")
public class AccountController {

    @Autowired
    private AccountService accountService;

    /**
     * 查询所有账户信息
     */
    @GetMapping
    @Operation(summary = "查询所有账户信息")
    public ResponseEntity<List<Map<String, Object>>> getAllAccounts() {
        List<Map<String, Object>> accounts = accountService.getAllAccounts();
        return new ResponseEntity<>(accounts, HttpStatus.OK);
    }

    /**
     * 添加新账户
     */
    @PostMapping
    @Operation(summary = "添加新账户")
    public ResponseEntity<Map<String, Object>> addAccount(@RequestBody Map<String, Object> accountData) {
        Map<String, Object> result = accountService.addAccount(accountData);
        return new ResponseEntity<>(result, HttpStatus.CREATED);
    }

    /**
     * 删除账户
     */
    @DeleteMapping("/{accountAlias}")
    @Operation(summary = "删除账户")
    public ResponseEntity<Map<String, Object>> deleteAccount(@PathVariable String accountAlias) {
        Map<String, Object> result = accountService.deleteAccount(accountAlias);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}

